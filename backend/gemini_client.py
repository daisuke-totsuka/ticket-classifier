"""Flask gateway that proxies the React front-end requests to Gemini.

The endpoint `/api/gemini` expects a JSON payload that contains a
`ticket` field and responds with the structured fields that the UI
already understands (label, reason, action, etc.).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, jsonify, request
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not API_KEY:
    raise EnvironmentError(
        "Gemini API key is missing. Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable."
    )

genai.configure(api_key=API_KEY)
MODEL = genai.GenerativeModel("gemini-2.5-flash")


PROMPT_TEMPLATE = """あなたはヘルプデスクの一次分類AIです。以下のチケット本文を分析し、必ず厳密なJSONのみで返答してください。説明文やマークダウンは不要です。

【目的】
- チケットを以下の項目に分類します。
  label: 分類ラベル（例: 障害対応 / 機能要望 / 質問 / その他）
  reason: 分類の理由（150〜400文字程度）
  action: 推奨される対応（調査手順/暫定回避/恒久対策）
  confidence: 0.0〜1.0の信頼度（数値）
  title: 短く明確なタイトル
  related: 3〜6個の関連語を配列で

【安全ガード】
- 個人情報（氏名・住所・電話・メールなど）は出力せず "[PII]" に置換。
- 資格情報やトークン、URLキーなどは "[SECRET]" に置換。
- 有害・暴力的・性的・差別的な表現は出力しない。
- 実在人物や組織を断定的に批評しない。
- 医療・法律・犯罪・政治的な助言を行わない。

【分類不能時の出力ルール】
- 内容が曖昧・挨拶文・ノイズなどで分類できない場合も、必ず次のJSONを返す:
  {"label":"エラー","title":"その他（要トリアージ）","reason":"入力内容が分類に適さないため要確認。","action":"","confidence":0.0,"related":[]}

【出力形式（STRICT JSON ONLY）】
- 出力はJSONのみ（キー: label, reason, action, confidence, title, related）
- コードフェンス（```）や説明文は付けない。
- 前後に文を追加しない。出力例以外の文字は一切含めない。

チケット内容:
{ticket}
"""


class GeminiClientError(RuntimeError):
    """Custom exception for Gemini client issues."""


def _extract_text_parts(response: Any) -> Tuple[Optional[str], Optional[str]]:
    """Extract primary text and finish reason from the Gemini response."""
    try:
        candidates = getattr(response, "candidates", None)
        if not candidates:
            return None, None
        candidate = candidates[0]
        parts = getattr(getattr(candidate, "content", None), "parts", None)
        if not parts:
            return None, getattr(candidate, "finish_reason", None)
        texts = [getattr(part, "text", "") for part in parts]
        text = "".join(texts).strip() or None
        finish_reason = getattr(candidate, "finish_reason", None)
        return text, finish_reason
    except Exception as exc:  # pragma: no cover - defensive against SDK changes
        raise GeminiClientError("Failed to read Gemini response") from exc


def _parse_json_payload(raw_text: str) -> Tuple[str, str, str, str, List[str], Optional[float]]:
    """Parse the JSON payload returned by Gemini, being tolerant to wrappers."""
    text = raw_text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.strip("`\n")
        if "\n" in text:
            text = text.split("\n", 1)[1]
    if "{" in text and "}" in text:
        text = text[text.find("{"): text.rfind("}") + 1]

    payload: Dict[str, Any] = json.loads(text)
    label = str(payload.get("label", "")).strip()
    reason = str(payload.get("reason", "")).strip()
    action = str(payload.get("action", "")).strip()
    title = str(payload.get("title", "")).strip()

    related_values: List[str] = []
    related_raw = payload.get("related", [])
    if isinstance(related_raw, list):
        related_values = [str(item).strip() for item in related_raw if str(item).strip()]
    elif isinstance(related_raw, str) and related_raw.strip():
        related_values = [item.strip() for item in related_raw.split(",") if item.strip()]

    confidence_value: Optional[float] = None
    if payload.get("confidence") is not None:
        try:
            confidence_value = float(payload.get("confidence"))
        except (TypeError, ValueError):
            confidence_value = None

    return label, reason, action, title, related_values, confidence_value


@app.post("/api/gemini")
def classify_ticket():
    data = request.get_json(silent=True) or {}
    ticket = (data.get("ticket") or data.get("text") or "").strip()

    if not ticket:
        return (
            jsonify(
                {
                    "result": "エラー",
                    "label": "エラー",
                    "reason": "入力が空です。",
                    "action": "",
                    "title": "",
                    "confidence": None,
                    "meta": None,
                    "related": [],
                }
            ),
            400,
        )

    try:
        response = MODEL.generate_content(
            PROMPT_TEMPLATE.format(ticket=ticket),
            generation_config=genai.types.GenerationConfig(
                temperature=0,
                max_output_tokens=768,
            ),
        )

        raw_text, finish_reason = _extract_text_parts(response)
        if not raw_text:
            return (
                jsonify(
                    {
                        "result": "エラー",
                        "raw": f"finish_reason={finish_reason}",
                        "label": "エラー",
                        "reason": "AI応答が取得できませんでした。入力を確認して再試行してください。",
                        "action": "",
                        "title": "",
                        "confidence": None,
                        "meta": None,
                        "related": [],
                    }
                ),
                502,
            )

        try:
            label, reason, action, title, related, confidence = _parse_json_payload(raw_text)
        except Exception:
            label = raw_text
            reason = "JSON解析に失敗しました"
            action = ""
            title = ""
            related = []
            confidence = None

        usage_meta = None
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            usage_meta = {
                "prompt_token_count": getattr(usage, "prompt_token_count", None),
                "candidates_token_count": getattr(usage, "candidates_token_count", None),
                "total_token_count": getattr(usage, "total_token_count", None),
            }

        return jsonify(
            {
                "result": label,
                "raw": raw_text,
                "label": label,
                "reason": reason,
                "action": action,
                "title": title,
                "confidence": confidence,
                "related": related,
                "meta": {"usage": usage_meta},
            }
        )

    except Exception as exc:  # pragma: no cover - network/SDK errors
        return (
            jsonify(
                {
                    "result": "エラー",
                    "label": "エラー",
                    "reason": f"AI呼び出しでエラーが発生しました: {exc}",
                    "action": "",
                    "title": "",
                    "confidence": None,
                    "meta": None,
                    "related": [],
                }
            ),
            500,
        )


@app.get("/api/health")
def health() -> Tuple[str, int]:
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))