import React, { useState } from "react";
import "./App.css";

function App() {
  const [ticket, setTicket] = useState("");
  const [result, setResult] = useState("");
  const [raw, setRaw] = useState("");
  const [meta, setMeta] = useState(null);
  const [label, setLabel] = useState("");
  const [reason, setReason] = useState("");
  const [title, setTitle] = useState("");
  const [relatedFromApi, setRelatedFromApi] = useState([]);
  const [action, setAction] = useState("");
  const [confidence, setConfidence] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!ticket.trim()) {
      alert("チケット内容を入力してください");
      return;
    }

    // 直前の分類結果をクリア
    setResult("");
    setRaw("");
    setMeta(null);
    setLabel("");
    setReason("");
    setAction("");
    setTitle("");
    setRelatedFromApi([]);
    setConfidence(null);

    setLoading(true);
    try {
      //const response = await fetch("http://localhost:5000/api/ask", {
      //const response = await fetch("http://localhost:5000/predict", {
      const baseUrl =
        process.env.REACT_APP_GEMINI_CLIENT_BASE_URL || "http://localhost:8000";
      const endpoint = `${baseUrl.replace(/\/$/, "")}/api/gemini`;

      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticket }),
      });

      if (!response.ok) {
        const errorBody = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorBody}`);
      }

      const data = await response.json();
      setResult(data.result);
      setRaw(data.raw || "");
      setMeta(data.meta || null);
      setLabel(data.label || "");
      setReason(data.reason || "");
      setAction(data.action || "");
      setTitle(data.title || "");
      setRelatedFromApi(Array.isArray(data.related) ? data.related : []);
      setConfidence(
        typeof data.confidence === "number"
          ? Math.max(0, Math.min(1, data.confidence))
          : null
      );
    } catch (error) {
      const message =
        error instanceof Error
          ? `エラー: サーバーに接続できませんでした (${error.message})`
          : "エラー: サーバーに接続できませんでした";
      setResult(message);
      setRaw("");
      setMeta(null);
      setLabel("");
      setReason("");
      setAction("");
      setTitle("");
      setRelatedFromApi([]);
      setConfidence(null);
    } finally {
      setLoading(false);
    }
  };

  // 分類タイトルと連想しやすい関連タイトル候補を生成
  const getCategoryInfo = (lbl) => {
    const normalized = (lbl || "").toLowerCase();
    if (!normalized) return { title: "", related: [] };
    if (normalized.includes("障害")) {
      return {
        title: "インシデント / 障害対応",
        related: ["サービス停止", "エラー調査", "復旧対応", "恒久対策"],
      };
    }
    if (normalized.includes("問") || normalized.includes("問い合わせ")) {
      return {
        title: "一般的な問い合わせ / 利用相談",
        related: ["使い方", "仕様確認", "アカウント/請求", "設定変更"],
      };
    }
    return {
      title: "その他（要トリアージ）",
      related: ["改善提案", "要件確認", "運用依頼", "情報提供"],
    };
  };
  const categoryInfo = title
    ? { title, related: relatedFromApi }
    : getCategoryInfo(label);
  // 推奨対応(action)を配列に整形（JSON配列/オブジェクトにも対応し、括弧やカンマ・画像は表示しない）
  const actionItems = (() => {
    const raw = (action || "").trim();
    if (!raw) return [];

    // 画像（Markdown/HTML/直接URL）を除去
    const stripImages = (text) =>
      text
        // Markdown image ![alt](url)
        .replace(/!\[[^\]]*\]\([^\)]*\)/gi, "")
        // HTML <img ...>
        .replace(/<img[\s\S]*?>/gi, "")
        // 画像ファイルへの直接URL
        .replace(/https?:\/\/\S+\.(?:png|jpe?g|gif|webp|svg)(?=\s|$)/gi, "");

    const rawNoImages = stripImages(raw);

    // 1) まずJSONとして解釈を試みる
    try {
      const candidate = rawNoImages
        .replace(/^```(?:json)?/i, "")
        .replace(/```$/i, "")
        .trim();
      if (
        (candidate.startsWith("[") && candidate.endsWith("]")) ||
        (candidate.startsWith("{") && candidate.endsWith("}"))
      ) {
        const parsed = JSON.parse(candidate);
        // 配列: ["...", "..."]
        if (Array.isArray(parsed)) {
          return parsed
            .map((s) => String(s).replace(/\\n/g, "\n").trim())
            .filter(Boolean);
        }
        // オブジェクト: { steps: ["..."], actions: ["..."] など }
        if (parsed && typeof parsed === "object") {
          const possibleKeys = ["steps", "actions", "items", "procedure"];
          for (const key of possibleKeys) {
            if (Array.isArray(parsed[key])) {
              return parsed[key]
                .map((s) => String(s).replace(/\\n/g, "\n").trim())
                .filter(Boolean);
            }
          }
          // 値が配列/文字列のオブジェクト → 値を列挙
          const values = Object.values(parsed).flat();
          if (values && values.length) {
            return values
              .map((v) => String(v).replace(/\\n/g, "\n").trim())
              .filter(Boolean);
          }
        }
      }
    } catch (_) {
      // JSON解釈に失敗したら後続のテキスト分割にフォールバック
    }

    // 2) テキスト箇条書きを行ごとに分割（括弧・カンマ・\nリテラルを除去）
    const normalized = rawNoImages
      .replace(/\r\n/g, "\n")
      .replace(/\\n/g, "\n")
      // 1) / 1. / (1) などの番号を区切りとして改行に変換
      .replace(/\s*(?:\(|\b)?\d+[\.)]\s*/g, "\n")
      // 箇条書き記号を改行に変換
      .replace(/[・•\-]\s*/g, "\n")
      // 配列/オブジェクトの括弧やカンマを除去
      .replace(/[\[\]{}]/g, "")
      .replace(/\s*,\s*/g, "\n")
      .trim();
    return normalized
      .split(/\n+/)
      .map((s) =>
        s
          .replace(/^[-・•]\s*/, "")
          .replace(/^"|"$/g, "")
          .replace(/^'|'$/g, "")
          .trim()
      )
      .filter(Boolean);
  })();

  return (
    <div
      style={{
        maxWidth: 800,
        margin: "40px auto",
        fontFamily: "sans-serif",
        padding: "0 20px",
      }}
    >
      <h1 style={{ textAlign: "center", color: "#333" }}>
        🎫 チケット分類アプリ
      </h1>
      <p style={{ textAlign: "center", color: "#666", marginBottom: "30px" }}>
        Powered by Google Gemini AI
      </p>

      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: "20px" }}>
          <label
            htmlFor="ticket"
            style={{
              display: "block",
              marginBottom: "10px",
              fontWeight: "bold",
            }}
          >
            チケット内容:
          </label>
          <textarea
            id="ticket"
            value={ticket}
            onChange={(e) => setTicket(e.target.value)}
            rows={6}
            placeholder="例: ユーザーがログインできないという問題が発生しています。エラーメッセージは「パスワードが正しくありません」と表示されます。"
            style={{
              width: "100%",
              fontSize: "1rem",
              padding: "12px",
              border: "1px solid #ddd",
              borderRadius: "4px",
              resize: "vertical",
            }}
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          style={{
            padding: "12px 24px",
            fontSize: "1rem",
            backgroundColor: loading ? "#ccc" : "#007bff",
            color: "white",
            border: "none",
            borderRadius: "4px",
            cursor: loading ? "not-allowed" : "pointer",
            width: "100%",
          }}
        >
          {loading ? "分類中..." : "分類する"}
        </button>
      </form>

      {result && (
        <div
          style={{
            marginTop: "30px",
            padding: "20px",
            backgroundColor: "#f8f9fa",
            borderRadius: "4px",
            border: "1px solid #dee2e6",
          }}
        >
          {label && reason && (
            <>
              {/* 上段: 分類と信頼度を横並びで */}
              <div
                style={{
                  display: "flex",
                  gap: 24,
                  alignItems: "center",
                  marginBottom: 16,
                }}
              >
                <div>
                  <span
                    style={{
                      color: "#000",
                      fontWeight: "bold",
                      marginRight: 8,
                    }}
                  >
                    分類:
                  </span>
                  <span
                    style={{
                      background: "#e3f2fd",
                      border: "1px solid #bbdefb",
                      borderRadius: 4,
                      padding: "6px 16px",
                      fontSize: 18,
                    }}
                  >
                    {label}
                  </span>
                </div>
                {confidence !== null && (
                  <div>
                    <span
                      style={{
                        color: "#000",
                        fontWeight: "bold",
                        marginRight: 8,
                      }}
                    >
                      信頼度:
                    </span>
                    <span
                      style={{
                        background: "#e3f2fd",
                        border: "1px solid #bbdefb",
                        borderRadius: 4,
                        padding: "6px 16px",
                        fontSize: 18,
                      }}
                    >
                      {(confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                )}
              </div>
              {/* 分類タイトル */}
              {categoryInfo.title && (
                <div
                  style={{
                    display: "flex",
                    gap: 24,
                    alignItems: "center",
                    marginBottom: 16,
                  }}
                >
                  <span
                    style={{
                      color: "#000",
                      fontWeight: "bold",
                      marginRight: 8,
                      fontSize: 16,
                    }}
                  >
                    分類タイトル:
                  </span>
                  <span
                    style={{
                      background: "#e3f2fd",
                      border: "1px solid #bbdefb",
                      borderRadius: 4,
                      padding: "6px 16px",
                      fontSize: 18,
                      color: "#000",
                    }}
                  >
                    {categoryInfo.title}
                  </span>
                </div>
              )}
              {/* 理由と推奨対応を縦並びで */}
              <div style={{ marginBottom: 16 }}>
                <h4 style={{ margin: "0 0 8px 0", color: "#000" }}>理由:</h4>
                <p
                  style={{
                    margin: 0,
                    padding: "8px 12px",
                    backgroundColor: "#f3e5f5",
                    borderRadius: "4px",
                    border: "1px solid #ce93d8",
                  }}
                >
                  {reason}
                </p>
              </div>
              {action && (
                <div style={{ marginBottom: 0 }}>
                  <h4 style={{ margin: "0 0 8px 0", color: "#000" }}>
                    推奨される対応方法:
                  </h4>
                  <div
                    style={{
                      background: "#fff",
                      border: "1px solid #eee",
                      padding: "12px",
                      borderRadius: "4px",
                    }}
                  >
                    {actionItems.length > 0
                      ? actionItems.map((line, idx) => (
                          <div
                            key={idx}
                            style={{
                              display: "flex",
                              gap: 8,
                              alignItems: "flex-start",
                              marginBottom:
                                idx === actionItems.length - 1 ? 0 : 8,
                            }}
                          >
                            <span style={{ color: "#555", minWidth: 24 }}>
                              {idx + 1})
                            </span>
                            <span style={{ flex: 1 }}>{line}</span>
                          </div>
                        ))
                      : action}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default App;
