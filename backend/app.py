import os, json
from flask import Flask, request, jsonify, abort
from flask_cors import CORS
import google.generativeai as genai

# ===== 1) アプリ生成（staticはつけない：開発時は不要） =====
app = Flask(__name__)
# API 配下にだけ CORS を許可
#CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

mode = os.getenv("FLASK_ENV", "development")

if mode == "production":
    origins = ["https://daisuke-totsuka.github.io"]
else:
    origins = ["*"]

CORS(app, resources={r"/*": {"origins": origins}})

# ===== 2) ヘルスチェック =====
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

# ===== 3) Gemini 初期化（重複は削除） =====
API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not API_KEY:
    raise EnvironmentError(
        "Gemini APIキーが見つかりません。PowerShell で "
        "`$env:GEMINI_API_KEY=\"YOUR_KEY\"` または `$env:GOOGLE_API_KEY=\"YOUR_KEY\"` を設定してください。"
    )
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# ===== 4) 予測API（/api/predict と /api/ask を同一関数で受ける） =====
@app.route('/api/predict', methods=['POST'])
@app.route('/api/ask', methods=['POST'])
def predict():
    data = request.get_json() or {}
    ticket = data.get('ticket', '')

    # ★ダミー早期レスポンス（切り分け用）
    return jsonify({
        "result": "DUMMY",
        "raw": "dummy",
        "label": "テスト",
        "reason": "ルート到達確認のためのダミー応答",
        "action": "なし",
        "title": "到達OK",
        "confidence": 1.0,
        "meta": None
         }), 200
    
    prompt = (
        "次のチケット内容を分析し、厳密なJSONのみで返答してください。\n"
        "日本語で、以下のキーを必ず含めてください: label, reason, confidence, action, title, related。\n"
        "- label: 分類ラベル\n"
        "- reason: 150〜400文字程度で根拠を具体的に\n"
        "- action: 調査手順/暫定回避/恒久対策を簡潔に\n"
        "- confidence: 0.0〜1.0\n"
        "- title: 短く明確な分類タイトル\n"
        "- related: 3〜6個の関連語配列\n"
        "他の文字やマークダウン、説明は出力しないでください。\n"
        f"チケット内容: '{ticket}'\n"
        "出力例: {\"label\":\"障害対応\",\"reason\":\"...\",\"confidence\":0.82,"
        "\"action\":\"1) ログ採取 ...\",\"title\":\"インシデント / 障害対応\","
        "\"related\":[\"サービス停止\",\"エラー調査\",\"復旧対応\"]}"
    )

    try:
        resp = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0,
                max_output_tokens=768
            )
        )
        raw_text = (resp.text or "").strip()

        # --- JSON抽出 ---
        parsed = None
        try:
            s = raw_text.strip()
            if s.startswith("```") and s.endswith("```"):
                s = s.strip("`\n").split("\n", 1)[-1]
            if "{" in s and "}" in s:
                s = s[s.find("{"): s.rfind("}")+1]
            parsed = json.loads(s)
        except Exception:
            parsed = None

        if isinstance(parsed, dict):
            label = str(parsed.get("label", "")).strip()
            reason = str(parsed.get("reason", "")).strip()
            action = str(parsed.get("action", "")).strip()
            title  = str(parsed.get("title", "")).strip()
            rv = parsed.get("related", [])
            related = [str(x).strip() for x in rv] if isinstance(rv, list) else []
            try:
                confidence = float(parsed.get("confidence")) if parsed.get("confidence") is not None else None
            except Exception:
                confidence = None
        else:
            label = raw_text
            reason = "JSON解析に失敗しました"
            action = ""
            title  = ""
            related = []
            confidence = None

        # 返却
        usage = None
        try:
            if hasattr(resp, "usage_metadata") and resp.usage_metadata:
                usage = {
                    "prompt_token_count": getattr(resp.usage_metadata, "prompt_token_count", None),
                    "candidates_token_count": getattr(resp.usage_metadata, "candidates_token_count", None),
                    "total_token_count": getattr(resp.usage_metadata, "total_token_count", None),
                }
        except Exception:
            usage = None

        candidates = None
        try:
            if hasattr(resp, "candidates") and resp.candidates:
                candidates = []
                for c in resp.candidates:
                    candidates.append({
                        "finish_reason": getattr(c, "finish_reason", None),
                        "content": getattr(c, "content", None).parts[0].text
                                   if getattr(c, "content", None) and getattr(getattr(c, "content", None), "parts", None) else None,
                    })
        except Exception:
            candidates = None

        return jsonify({
            "result": label,
            "raw": raw_text,
            "label": label,
            "reason": reason,
            "action": action,
            "title": title,
            "confidence": confidence,
            "meta": {"usage": usage, "candidates": candidates}
        })

    except Exception as e:
        return jsonify({
            "result": f"エラー: {e}",
            "raw": str(e),
            "label": "エラー",
            "reason": f"エラーが発生しました: {e}",
            "action": "",
            "title": "",
            "confidence": None,
            "meta": None
        }), 500

# ===== 5) SPAキャッチオール（/api/* は触らない） =====
@app.route('/', defaults={'path': ''}, methods=['GET', 'OPTIONS'])
@app.route('/<path:path>', methods=['GET', 'OPTIONS'])
def serve_frontend(path):
    # /api/ から始まるパスはここで処理しない
    if request.path.startswith('/api/'):
        abort(404)
    return 'frontend placeholder', 200   # 開発中はプレースホルダで十分

# ===== 6) 最後に一度だけ run =====
if __name__ == '__main__':
    # 末尾スラッシュ差での取りこぼしを避けたい場合は次を有効化
    # app.url_map.strict_slashes = False
    app.run(host='0.0.0.0', port=5000, debug=True)
