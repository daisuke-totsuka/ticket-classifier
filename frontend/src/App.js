import React, { useState } from "react";
import "./App.css";

function App() {
  const [ticket, setTicket] = useState("");
  const [responseText, setResponseText] = useState("");
  const [structuredResult, setStructuredResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!ticket.trim()) {
      alert("チケット内容を入力してください");
      return;
    }
    // 直前の結果をクリア
    setResponseText("");
    setStructuredResult(null);
    setErrorMessage("");

    setLoading(true);
    try {
      //const baseUrl =
      //  process.env.REACT_APP_GEMINI_CLIENT_BASE_URL || "http://localhost:8000";
      //const endpoint = `${baseUrl.replace(/\/$/, "")}/api/gemini`;

      const baseUrl =
        process.env.REACT_APP_GEMINI_CLIENT_BASE_URL ||
        process.env.REACT_APP_API_BASE_URL ||
        "http://localhost:5000";
      const endpoint = `${baseUrl.replace(/\/$/, "")}/api/ask`;

      //const response = await fetch(endpoint, {
      const response = await fetch("http://localhost:5000/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: ticket }), // or { ticket }
      });

      if (!response.ok) {
        const errorBody = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorBody}`);
      }

      const data = await response.json();

      const rawText =
        typeof data.raw === "string" && data.raw.trim()
          ? data.raw
          : typeof data.result === "string"
          ? data.result
          : "";

      const parsed =
        data && typeof data.parsed === "object" && data.parsed !== null
          ? data.parsed
          : {};
      const segments = Array.isArray(data?.segments) ? data.segments : [];
      const reportedConfidence =
        typeof data.confidence === "number" && Number.isFinite(data.confidence)
          ? data.confidence
          : null;

      const toTrimmedString = (value) =>
        value === undefined || value === null ? "" : String(value).trim();

      const toNumberOrNull = (value) => {
        if (value === undefined || value === null) {
          return null;
        }
        const num = Number(value);
        return Number.isFinite(num) ? num : null;
      };

      const extractFromSegments = (keywords) => {
        for (const keyword of keywords) {
          const hit = segments.find(
            (segment) =>
              segment &&
              typeof segment.label === "string" &&
              segment.label.includes(keyword)
          );
          if (hit && hit.value !== undefined && hit.value !== null) {
            return toTrimmedString(hit.value);
          }
        }
        return "";
      };

      const segmentConfidenceText = extractFromSegments(["信頼度", "confidence"]);
      const parsedConfidenceText = toTrimmedString(parsed.gemini_confidence);
      const confidenceValue =
        reportedConfidence ??
        toNumberOrNull(parsedConfidenceText) ??
        toNumberOrNull(segmentConfidenceText);
      const confidenceText =
        confidenceValue !== null
          ? ""
          : parsedConfidenceText || segmentConfidenceText || "";

      const normalizedResult = {
        title:
          toTrimmedString(parsed.ticket_classification_title) ||
          extractFromSegments(["タイトル", "title"]),
        description:
          toTrimmedString(parsed.ticket_classification_content) ||
          extractFromSegments(["分類", "説明", "content"]),
        proposal:
          toTrimmedString(parsed.gemini_answer) ||
          extractFromSegments(["提案", "対応", "answer"]),
        confidence: confidenceValue,
        confidenceText,
      };

      const hasStructured = Object.values(normalizedResult).some(
        (value) => value !== null && value !== ""
      );
      setStructuredResult(hasStructured ? normalizedResult : null);

      if (rawText) {
        setResponseText(rawText);
      } else {
        setResponseText(JSON.stringify(data, null, 2));
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? `エラー: サーバーに接続できませんでした (${error.message})`
          : "エラー: サーバーに接続できませんでした";
      setErrorMessage(message);
      setResponseText("");
      setStructuredResult(null);
    } finally {
      setLoading(false);
    }
  };

  const formatConfidence = (value) => {
    if (value === null || Number.isNaN(value)) {
      return null;
    }
    if (value >= 0 && value <= 1) {
      return `${(value * 100).toFixed(1)}%`;
    }
    return value.toFixed(2);
  };

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
      {errorMessage && (
        <div
          style={{
            marginTop: "30px",
            padding: "20px",
            backgroundColor: "#fdecea",
            borderRadius: "4px",
            border: "1px solid #f5c2c7",
            color: "#b02a37",
          }}
        >
          {errorMessage}
        </div>
      )}

      {structuredResult ? (
        <div
          style={{
            marginTop: "30px",
            padding: "20px",
            backgroundColor: "#f8f9fa",
            borderRadius: "4px",
            border: "1px solid #dee2e6",
          }}
        >
          <h2 style={{ marginTop: 0, color: "#000" }}>Gemini API 応答</h2>
          <div style={{ marginBottom: "16px" }}>
            <h3 style={{ margin: "0 0 8px", fontSize: "1.1rem", color: "#333" }}>
              タイトル
            </h3>
            <p
              style={{
                margin: 0,
                lineHeight: 1.6,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {structuredResult.title || "取得できませんでした"}
            </p>
          </div>
          <div style={{ marginBottom: "16px" }}>
            <h3 style={{ margin: "0 0 8px", fontSize: "1.1rem", color: "#333" }}>
              信頼度
            </h3>
            <p
              style={{
                margin: 0,
                lineHeight: 1.6,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                color: "#555",
              }}
            >
              {formatConfidence(structuredResult.confidence) ||
                structuredResult.confidenceText ||
                "取得できませんでした"}
            </p>
          </div>
          <div style={{ marginBottom: "16px" }}>
            <h3 style={{ margin: "0 0 8px", fontSize: "1.1rem", color: "#333" }}>
              分類説明
            </h3>
            <p
              style={{
                margin: 0,
                lineHeight: 1.6,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {structuredResult.description || "取得できませんでした"}
            </p>
          </div>
          <div>
            <h3 style={{ margin: "0 0 8px", fontSize: "1.1rem", color: "#333" }}>
              対応提案内容
            </h3>
            <p
              style={{
                margin: 0,
                lineHeight: 1.6,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {structuredResult.proposal || "取得できませんでした"}
            </p>
          </div>
          {responseText && (
            <details style={{ marginTop: "24px" }}>
              <summary style={{ cursor: "pointer", color: "#555" }}>
                生のレスポンスを表示
              </summary>
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  marginTop: "12px",
                  fontFamily: "monospace",
                  fontSize: "0.95rem",
                  color: "#212529",
                }}
              >
                {responseText}
              </pre>
            </details>
          )}
        </div>
      ) : (
        responseText && (
          <div
            style={{
              marginTop: "30px",
              padding: "20px",
              backgroundColor: "#f8f9fa",
              borderRadius: "4px",
              border: "1px solid #dee2e6",
            }}
          >
            <h2 style={{ marginTop: 0, color: "#000" }}>Gemini API 応答</h2>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                margin: 0,
                fontFamily: "monospace",
                fontSize: "0.95rem",
                color: "#212529",
              }}
            >
              {responseText}
            </pre>
          </div>
        )
      )}
    </div>
  );
}

export default App;
