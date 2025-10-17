import os, json, textwrap
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
    data = request.get_json(silent=True) or {}
    # フロントのキーが 'ticket' / 'text' どちらでも拾えるように
    ticket = (data.get('ticket') or data.get('text') or '').strip()

    if not ticket:
        return jsonify({
            "result": "エラー",
            "label": "エラー",
            "reason": "入力が空です。",
            "action": "",
            "title": "",
            "confidence": None,
            "meta": None
        }), 400

    prompt = textwrap.dedent(f"""
        あなたはヘルプデスクの一次分類AIです。以下のチケット本文を分析し、
        必ず厳密なJSONのみで返答してください。説明文やマークダウンは不要です。

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

        出力例:
        {"label":"障害対応","reason":"ログエラーが発生しサービスが停止しているため、障害対応と判断。","action":"1) ログ調査 2) 再起動実施 3) 原因解析","confidence":0.92,"title":"ログエラーによる障害","related":["サービス停止","復旧対応","調査"]}
    """).strip()

    def _safe_pick_text(response):
        try:
            cand = response.candidates[0] if getattr(response, 'candidates', None) else None
            finish = getattr(cand, 'finish_reason', None)
            feedback = getattr(response, 'prompt_feedback', None)

            if cand and getattr(cand, 'content', None) and getattr(cand.content, 'parts', None):
                parts = [p.text for p in cand.content.parts if hasattr(p, 'text')]
                txt = ''.join(parts).strip()
                return txt if txt else None, finish, feedback

            return None, finish, feedback
        except Exception:
            return None, None, None

    try:
        resp = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0,
                max_output_tokens=768
            )
        )

        raw_text, finish_reason, feedback = _safe_pick_text(resp)

        if not raw_text:
            return jsonify({
                "result": "エラー",
                "raw": f"finish_reason={finish_reason}",
                "label": "エラー",
                "reason": "安全性フィルターにより応答が返りませんでした。入力の機微情報を[PII]/[SECRET]に置換して再試行してください。",
                "action": "",
                "title": "",
                "confidence": None,
                "meta": {"feedback": str(feedback)}
            }), 502

        parsed = None
        try:
            s = raw_text.strip()
            if s.startswith('```') and s.endswith('```'):
                s = s.strip('`\n').split('\n', 1)[-1]
            if '{' in s and '}' in s:
                s = s[s.find('{'): s.rfind('}') + 1]
            parsed = json.loads(s)
        except Exception:
            parsed = None

        if isinstance(parsed, dict):
            label = str(parsed.get('label', '')).strip()
            reason = str(parsed.get('reason', '')).strip()
            action = str(parsed.get('action', '')).strip()
            title = str(parsed.get('title', '')).strip()
            rv = parsed.get('related', [])
            related = [str(x).strip() for x in rv] if isinstance(rv, list) else []
            try:
                confidence = float(parsed.get('confidence')) if parsed.get('confidence') is not None else None
            except Exception:
                confidence = None
        else:
            label = raw_text
            reason = 'JSON解析に失敗しました'
            action = ''
            title = ''
            related = []
            confidence = None

        usage = None
        try:
            if hasattr(resp, 'usage_metadata') and resp.usage_metadata:
                usage = {
                    'prompt_token_count': getattr(resp.usage_metadata, 'prompt_token_count', None),
                    'candidates_token_count': getattr(resp.usage_metadata, 'candidates_token_count', None),
                    'total_token_count': getattr(resp.usage_metadata, 'total_token_count', None),
                }
        except Exception:
            usage = None

        candidates = None
        try:
            if hasattr(resp, 'candidates') and resp.candidates:
                candidates = []
                for c in resp.candidates:
                    text_part = None
                    if getattr(c, 'content', None) and getattr(c.content, 'parts', None):
                        first_part = c.content.parts[0]
                        text_part = getattr(first_part, 'text', None)
                    candidates.append({
                        'finish_reason': getattr(c, 'finish_reason', None),
                        'content': text_part,
                    })
        except Exception:
            candidates = None

        return jsonify({
            'result': label,
            'raw': raw_text,
            'label': label,
            'reason': reason,
            'action': action,
            'title': title,
            'confidence': confidence,
            'meta': {'usage': usage, 'candidates': candidates}
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