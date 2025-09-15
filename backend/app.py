import os
import json
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2

app = Flask(__name__)
CORS(app)

# Gemini APIクライアントの初期化（APIキーは環境変数から取得）
# 優先順: GEMINI_API_KEY -> GOOGLE_API_KEY。どちらも無ければ明示エラー
API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not API_KEY:
    raise EnvironmentError(
        "Gemini APIキーが見つかりません。PowerShell で `$env:GEMINI_API_KEY=""YOUR_KEY""` または `$env:GOOGLE_API_KEY=""YOUR_KEY""` を設定してください。"
    )

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# PostgreSQL接続情報（必要に応じて環境変数や設定ファイルで管理してください）
DB_HOST = os.environ.get("PG_HOST", "localhost")
DB_PORT = os.environ.get("PG_PORT", "5432")
DB_NAME = os.environ.get("PG_DATABASE", "ticketdb")
DB_USER = os.environ.get("PG_USER", "postgres")
DB_PASS = os.environ.get("PG_PASSWORD", "Totsuka6218@")

@app.route('/predict', methods=['POST'])
def predict():
    data = request.get_json()
    ticket = data.get('ticket', '')

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
    
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0,
                max_output_tokens=768
            )
        )
        raw_text = response.text.strip()

        # JSON抽出と解析
        label = ""
        reason = ""
        action = ""
        title = ""
        related = []
        confidence = None
        parsed = None
        try:
            # コードフェンスが付く場合に備え除去
            candidate_text = raw_text.strip()
            if candidate_text.startswith("```") and candidate_text.endswith("```"):
                candidate_text = candidate_text.strip("`\n").split('\n', 1)[-1]
            # 先頭/末尾以外に文字が混ざる場合もあるので、最初の { から最後の } を抽出
            if '{' in candidate_text and '}' in candidate_text:
                candidate_text = candidate_text[candidate_text.find('{'):candidate_text.rfind('}')+1]
            parsed = json.loads(candidate_text)
        except Exception:
            parsed = None

        if isinstance(parsed, dict):
            label = str(parsed.get('label', '')).strip()
            reason = str(parsed.get('reason', '')).strip()
            action = str(parsed.get('action', '')).strip()
            title = str(parsed.get('title', '')).strip()
            try:
                rel_val = parsed.get('related', [])
                if isinstance(rel_val, list):
                    related = [str(x).strip() for x in rel_val if str(x).strip()]
                elif isinstance(rel_val, str):
                    # カンマ区切り文字列にも耐性
                    related = [s.strip() for s in rel_val.split(',') if s.strip()]
            except Exception:
                related = []
            try:
                confidence = float(parsed.get('confidence')) if parsed.get('confidence') is not None else None
            except Exception:
                confidence = None
        else:
            # 解析失敗時は生テキストをlabelに
            label = raw_text
            reason = "JSON解析に失敗しました"
            action = ""
            title = ""
            related = []
            confidence = None

        result = label
        
        # メタ情報抽出
        usage = None
        try:
            if hasattr(response, "usage_metadata") and response.usage_metadata is not None:
                usage = {
                    "prompt_token_count": getattr(response.usage_metadata, "prompt_token_count", None),
                    "candidates_token_count": getattr(response.usage_metadata, "candidates_token_count", None),
                    "total_token_count": getattr(response.usage_metadata, "total_token_count", None),
                }
        except Exception:
            usage = None

        prompt_feedback = None
        try:
            if hasattr(response, "prompt_feedback") and response.prompt_feedback is not None:
                prompt_feedback = {
                    "block_reason": getattr(response.prompt_feedback, "block_reason", None),
                    "safety_ratings": [
                        {
                            "category": getattr(r, "category", None),
                            "probability": getattr(r, "probability", None),
                        }
                        for r in getattr(response.prompt_feedback, "safety_ratings", []) or []
                    ],
                }
        except Exception:
            prompt_feedback = None

        candidates = None
        try:
            if hasattr(response, "candidates") and response.candidates is not None:
                candidates = []
                for c in response.candidates:
                    candidates.append(
                        {
                            "finish_reason": getattr(c, "finish_reason", None),
                            "safety_ratings": [
                                {
                                    "category": getattr(r, "category", None),
                                    "probability": getattr(r, "probability", None),
                                }
                                for r in getattr(c, "safety_ratings", []) or []
                            ],
                            "content": getattr(c, "content", None).parts[0].text if getattr(c, "content", None) and getattr(getattr(c, "content", None), "parts", None) else None,
                        }
                    )
        except Exception:
            candidates = None
            
    except Exception as e:
        result = f"エラー: {str(e)}"
        raw_text = result
        label = result
        reason = f"エラーが発生しました: {str(e)}"
        action = ""
        title = ""
        related = []
        confidence = None
        usage = None
        prompt_feedback = None
        candidates = None

    # --- ここからDB登録処理 ---
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tickets (input_text, label, reason, confidence, recommended_action)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (ticket, label, reason, confidence, action)
                )
        conn.close()
    except Exception as db_exc:
        print(f"[DB ERROR] {db_exc}")
    # --- DB登録ここまで ---

    return jsonify({
        'result': result, 
        'raw': raw_text,
        'label': label,
        'reason': reason,
        'action': action,
        'title': title,
        'confidence': confidence,
        'meta': { 
            'usage': usage, 
            'prompt_feedback': prompt_feedback, 
            'candidates': candidates 
        }
    })

if __name__ == '__main__':
    app.run(debug=True)