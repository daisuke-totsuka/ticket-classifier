import os, json, traceback
from http.server import BaseHTTPRequestHandler
import google.generativeai as genai

def _json_response(handler: BaseHTTPRequestHandler, code: int, obj: dict):
    body = json.dumps(obj).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(body)

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # --- 入力取得 ---
        try:
            n = int(self.headers.get("content-length", 0))
        except Exception:
            n = 0
        raw = self.rfile.read(n) if n > 0 else b"{}"
        try:
            data = json.loads(raw)
        except Exception:
            return _json_response(self, 400, {"error": "Invalid JSON"})

        ticket = (data.get("ticket") or "").strip()
        if not ticket:
            return _json_response(self, 400, {"error": "field 'ticket' is required"})

        # --- APIキー設定（GEMINI_API_KEY 優先、なければ GOOGLE_API_KEY） ---
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return _json_response(self, 500, {"error": "Missing GEMINI_API_KEY/GOOGLE_API_KEY"})

        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")

            # --- backend/app.py と同等のプロンプトを構築 ---
            prompt = (
                "次のチケット内容を分析し、厳密なJSONのみで返答してください。\n"
                "日本語で、以下のキーを必ず含めてください: label, reason, confidence, action, title, related。\n"
                "- label: 分類ラベル（例: '問い合わせ' / '障害対応' / 'その他' など任意）\n"
                "- reason: その分類にした理由。省略せず、根拠（症状・影響範囲・再現条件・関連コンポーネント等）を具体的に記述。最低でも150文字以上、可能なら200〜400文字程度。\n"
                "- action: 推奨される対応方法。調査手順・暫定回避策・恒久対策の順で箇条書き風に簡潔に。\n"
                "- confidence: 0.0〜1.0 の信頼度（数値）\n"
                "- title: チケット内容からユーザーにとって分かりやすく、関連も想起しやすい分類タイトル（短く明確に）\n"
                "- related: titleに関連する語やラベルを3〜6個の配列で（例: ['サービス停止','復旧対応',...]）\n"
                "他の文字やマークダウン、説明は一切出力しないでください。\n"
                f"チケット内容: '{ticket}'\n"
                "出力例: {\"label\": \"障害対応\", \"reason\": \"ログイン処理で…\", \"confidence\": 0.82, \"action\": \"1) ログ採取...\", \"title\": \"インシデント / 障害対応\", \"related\": [\"サービス停止\", \"エラー調査\", \"復旧対応\"]}"
            )

            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0,
                    max_output_tokens=768
                )
            )
            raw_text = (response.text or "").strip()

            # --- 厳密JSONの抽出・パース（コードフェンス/前後ノイズに耐性） ---
            parsed = None
            try:
                candidate_text = raw_text.strip()
                if candidate_text.startswith("```") and candidate_text.endswith("```"):
                    candidate_text = candidate_text.strip("`\n").split("\n", 1)[-1]
                if "{" in candidate_text and "}" in candidate_text:
                    candidate_text = candidate_text[candidate_text.find("{"):candidate_text.rfind("}")+1]
                parsed = json.loads(candidate_text)
            except Exception:
                parsed = None

            # --- フィールドを安全に取り出し ---
            label = reason = action = title = ""
            related = []
            confidence = None

            if isinstance(parsed, dict):
                label = str(parsed.get("label", "")).strip()
                reason = str(parsed.get("reason", "")).strip()
                action = str(parsed.get("action", "")).strip()
                title = str(parsed.get("title", "")).strip()
                try:
                    rel_val = parsed.get("related", [])
                    if isinstance(rel_val, list):
                        related = [str(x).strip() for x in rel_val if str(x).strip()]
                    elif isinstance(rel_val, str):
                        related = [s.strip() for s in rel_val.split(",") if s.strip()]
                except Exception:
                    related = []
                try:
                    if parsed.get("confidence") is not None:
                        confidence = float(parsed.get("confidence"))
                except Exception:
                    confidence = None
                result = label
            else:
                # 解析失敗時は生テキストを返す
                result = raw_text
                reason = "JSON解析に失敗しました"

            # --- メタ情報を詰める（使用トークン等） ---
            usage = None
            try:
                um = getattr(response, "usage_metadata", None)
                if um is not None:
                    usage = {
                        "prompt_token_count": getattr(um, "prompt_token_count", None),
                        "candidates_token_count": getattr(um, "candidates_token_count", None),
                        "total_token_count": getattr(um, "total_token_count", None),
                    }
            except Exception:
                usage = None

            prompt_feedback = None
            try:
                pf = getattr(response, "prompt_feedback", None)
                if pf is not None:
                    prompt_feedback = {
                        "block_reason": getattr(pf, "block_reason", None),
                        "safety_ratings": [
                            {"category": getattr(r, "category", None),
                             "probability": getattr(r, "probability", None)}
                            for r in (getattr(pf, "safety_ratings", []) or [])
                        ],
                    }
            except Exception:
                prompt_feedback = None

            candidates = None
            try:
                cs = getattr(response, "candidates", None)
                if cs:
                    candidates = []
                    for c in cs:
                        content = None
                        if getattr(c, "content", None) and getattr(c.content, "parts", None):
                            content = c.content.parts[0].text
                        candidates.append({
                            "finish_reason": getattr(c, "finish_reason", None),
                            "safety_ratings": [
                                {"category": getattr(r, "category", None),
                                 "probability": getattr(r, "probability", None)}
                                for r in (getattr(c, "safety_ratings", []) or [])
                            ],
                            "content": content,
                        })
            except Exception:
                candidates = None

            # --- 応答 ---
            return _json_response(self, 200, {
                "result": result,
                "raw": raw_text,
                "label": label,
                "reason": reason,
                "action": action,
                "title": title,
                "confidence": confidence,
                "meta": {
                    "usage": usage,
                    "prompt_feedback": prompt_feedback,
                    "candidates": candidates
                }
            })

        except Exception as e:
            print("ERROR:", traceback.format_exc())  # Vercel Runtime Logs に出ます
            return _json_response(self, 500, {"error": str(e)})

    # GET等は405に
    def do_GET(self):
        _json_response(self, 405, {"error": "Method Not Allowed"})
