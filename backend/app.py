import json
import os
import re

from flask import Flask, jsonify, request
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not API_KEY:
    raise RuntimeError("Gemini APIキーが設定されていません。")

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")


def _strip_code_fences(text: str) -> str:
    """Remove Markdown code fences if Gemini wraps the JSON response."""
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return text


def _extract_json_payload(text: str) -> dict:
    """Try to parse JSON out of Gemini's response."""
    cleaned = _strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start != -1 and end != -1 and end > start:
            fragment = cleaned[start : end + 1]
            return json.loads(fragment)
        raise


def _coerce_confidence(value):
    """Convert confidence-like values to float when possible."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
            if match:
                try:
                    return float(match.group())
                except ValueError:
                    return None
    return None


def _format_payload_for_humans(payload: dict) -> tuple[str, list[dict[str, str]], float | None]:
    """Build a human-friendly view from the Gemini JSON payload."""
    field_labels = {
        "ticket_classification_title": "分類タイトル",
        "ticket_classification_content": "分類内容",
        "gemini_confidence": "Gemini信頼度",
        "gemini_answer": "Geminiの提案内容",
    }

    segments: list[dict[str, str]] = []
    confidence_value = None

    for key, label in field_labels.items():
        if key not in payload:
            continue
        value = payload[key]
        if value is None:
            continue

        if key == "gemini_confidence":
            parsed_confidence = _coerce_confidence(value)
            if parsed_confidence is not None:
                confidence_value = parsed_confidence

        if isinstance(value, float):
            value_str = f"{value:.2f}"
        elif isinstance(value, (list, dict)):
            value_str = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            value_str = str(value).strip()
        segments.append({"label": label, "value": value_str})

    for key, value in payload.items():
        if key in field_labels:
            continue
        value_str = json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (list, dict)) else str(value).strip()
        segments.append({"label": key, "value": value_str})

    formatted = "\n\n".join(f"{segment['label']}:\n{segment['value']}" for segment in segments if segment["value"])
    return formatted, segments, confidence_value



@app.route("/api/health", methods=["GET"])
def health() -> tuple:
    return jsonify({"status": "ok"})


@app.route("/api/ask", methods=["POST"])
def ask() -> tuple:
    data = request.get_json(silent=True) or {}
    ticket = data.get("ticket") or data.get("text")
    if not ticket:
        return jsonify({"error": "ticketが必要です。"}), 400

    prompt = (
        "以下のチケット内容を分析してください。出力は必ず次のJSON形式で返してください。\n"
        "{\n"
        '  "ticket_classification_title": "短いタイトル",\n'
        '  "ticket_classification_content": "分類の説明",\n'
        '  "gemini_confidence": 0.0,\n'
        '  "gemini_answer": "Geminiの提案内容"\n'
        "}\n"
        "各フィールドは日本語で記載し、gemini_confidenceは0から1の間の数値で小数点以下2桁程度にしてください。\n"
        "チケット内容:\n"
        f"{ticket}"
    )

    try:
        response = model.generate_content(prompt)
    except Exception as exc:  # pragma: no cover - API呼び出し時の例外
        return jsonify({"error": f"Gemini API呼び出しに失敗しました: {exc}"}), 502

    text = (getattr(response, "text", None) or "").strip()

    if not text:
        return jsonify({"error": "Geminiの応答が空でした", "raw": text}), 502

    try:
        payload = _extract_json_payload(text)
    except json.JSONDecodeError:
        return jsonify({"error": "Geminiの応答をJSONとして解釈できませんでした", "raw": text}), 502

    formatted_text, segments, confidence = _format_payload_for_humans(payload)

    return jsonify({
        "raw": text,
        "raw_response": text,
        "parsed": payload,
        "segments": segments,
        "result": formatted_text or text,
        "confidence": confidence if confidence is not None else _coerce_confidence(payload.get("gemini_confidence")),
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
