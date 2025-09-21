# api/app.py
from flask import Flask, request, jsonify
import os, sys, pathlib

# 既存モジュールをimportできるように、プロジェクトルートをパスに追加
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

# 例: 既存の推論関数をインポート
# from ticket_classifier import load_model, predict_label
# model = load_model()

app = Flask(__name__)

@app.get("/")
def health():
    return jsonify({"ok": True})

#@app.post("/api/predict")
#def predict():
#    data = request.get_json(force=True) or {}
#    text = data.get("text", "")
#    if not text:
#        return jsonify({"error":"text is required"}), 400
#    # label = predict_label(model, text)
#    label = "billing" if "bill" in text.lower() else "other"   # 仮
#    return jsonify({"label": label})

if __name__ == "__main__":
    # ★ローカル検証用（Vercelでは無視される）
    app.run(host="127.0.0.1", port=3001, debug=True)
