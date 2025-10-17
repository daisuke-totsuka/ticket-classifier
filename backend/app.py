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
# ✅ デバッグ用ログ出力（Renderログで確認できる）
print("=== GEMINI_API_KEY loaded:", bool(API_KEY))
print("=== GEMINI_API_KEY value (masked):", API_KEY[:5] + "*****" if API_KEY else "None")
if not API_KEY:
    raise EnvironmentError(
        "Gemini APIキーが見つかりません。PowerShell で "
        "`$env:GEMINI_API_KEY=\"YOUR_KEY\"` または `$env:GOOGLE_API_KEY=\"YOUR_KEY\"` を設定してください。"
    )
genai.configure(api_key=API_KEY)
#model = genai.GenerativeModel('gemini-1.5-flash')
model = genai.GenerativeModel('gemini-2.5-flash')

# ===== 4) 予測API（/api/predict と /api/ask を同一関数で受ける） =====
@app.route('/api/predict', methods=['POST'])
@app.route('/api/ask', methods=['POST'])
def predict():
    data = request.get_json() or {}
    ticket = data.get('ticket', '')

    # ★ダミー早期レスポンス（切り分け用）
    #return jsonify({
    #    "result": "DUMMY",
    #    "raw": "dummy",
    #    "label": "テスト",
    #    "reason": "ルート到達確認のためのダミー応答",
    #    "action": "なし",
    #    "title": "到達OK",
    #    "confidence": 1.0,
    #    "meta": None
    #     }), 200
    
    #prompt = (
      #  "次のチケット内容を分析し、厳密なJSONのみで返答してください。\n"
      #  "日本語で、以下のキーを必ず含めてください: label, reason, confidence, action, title, related。\n"
      #  "- label: 分類ラベル\n"
      #  "- reason: 150〜400文字程度で根拠を具体的に\n"
      #  "- action: 調査手順/暫定回避/恒久対策を簡潔に\n"
      #  "- confidence: 0.0〜1.0\n"
      #  "- title: 短く明確な分類タイトル\n"
      #  "- related: 3〜6個の関連語配列\n"
      # "他の文字やマークダウン、説明は出力しないでください。\n"
      # f"チケット内容: '{ticket}'\n"
      # "チケット内容: '{ticket}'\n"
      #  "出力例: {\"label\":\"障害対応\",\"reason\":\"...\",\"confidence\":0.82,"
      # "\"action\":\"1) ログ採取 ...\",\"title\":\"インシデント / 障害対応\","
      # "\"related\":[\"サービス停止\",\"エラー調査\",\"復旧対応\"]}"
    #)
    prompt = (
    "あなたはヘルプデスクの一次分類AIです。以下のチケット本文を分析し、"
    "必ず厳密なJSONのみで返答してください。説明文やマークダウンは不要です。\n\n"
    "【目的】\n"
    "- チケットを以下の項目に分類します。\n"
    "  label: 分類ラベル（例: 障害対応 / 機能要望 / 質問 / その他）\n"
    "  reason: 分類の理由（150〜400文字程度）\n"
    "  action: 推奨される対応（調査手順/暫定回避/恒久対策）\n"
    "  confidence: 0.0〜1.0の信頼度（数値）\n"
    "  title: 短く明確なタイトル\n"
    "  related: 3〜6個の関連語を配列で\n\n"
    "【安全ガード】\n"
    "- 個人情報（氏名・住所・電話・メールなど）は出力せず \"[PII]\" に置換。\n"
    "- 資格情報やトークン、URLキーなどは \"[SECRET]\" に置換。\n"
    "- 有害・暴力的・性的・差別的な表現は出力しない。\n"
    "- 実在人物や組織を断定的に批評しない。\n"
    "- 医療・法律・犯罪・政治的な助言を行わない。\n\n"
    "【分類不能時の出力ルール】\n"
    "- 内容が曖昧・挨拶文・ノイズなどで分類できない場合も、必ず次のJSONを返す:\n"
    "{\"label\":\"エラー\",\"title\":\"その他（要トリアージ）\","
    "\"reason\":\"入力内容が分類に適さないため要確認。\",\"action\":\"\","
    "\"confidence\":0.0,\"related\":[]}\n\n"
    "【出力形式（STRICT JSON ONLY）】\n"
    "- 出力はJSONのみ（キー: label, reason, action, confidence, title, related）\n"
    "- コードフェンス（```）や説明文は付けない。\n"
    "- 前後に文を追加しない。出力例以外の文字は一切含めない。\n\n"
    f"チケット内容:\n{ticket}\n\n"
    "出力例:\n"
    "{\"label\":\"障害対応\",\"reason\":\"ログエラーが発生しサービスが停止しているため、障害対応と判断。\","
    "\"action\":\"1) ログ調査 2) 再起動実施 3) 原因解析\","
    "\"confidence\":0.92,\"title\":\"ログエラーによる障害\",\"related\":[\"サービス停止\",\"復旧対応\",\"調査\"]}"
)


    try:
        resp = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0,
                max_output_tokens=768
            )
        )
        #cands = getattr(resp, "candidates", None) or []
        #if not cands:
        #  fb = getattr(resp, "prompt_feedback", None)
        #  reason = getattr(fb, "block_reason", None) if fb else None
        #  # ここで安全ブロック時の文言やリトライ方針を返す
        # return jsonify({"error": "AI出力がブロックされました", "block_reason": str(reason)}), 400

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
