import json
import os

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
        "以下のチケット内容を分析し、JSON形式だけで回答してください。\n"
        f"{ticket}"
    )

    try:
        response = model.generate_content(prompt)
    except Exception as exc:  # pragma: no cover - API呼び出し時の例外
        return jsonify({"error": f"Gemini API呼び出しに失敗しました: {exc}"}), 502

    text = (getattr(response, "text", None) or "").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return jsonify({"error": "Geminiの応答をJSONとして解釈できませんでした。", "raw": text}), 502

    return jsonify(payload)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))