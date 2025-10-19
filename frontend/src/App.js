import React, { useState } from "react";
import "./App.css";

function App() {
  const [ticket, setTicket] = useState("");
  const [responseText, setResponseText] = useState("");
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
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticket }),
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
    } finally {
      setLoading(false);
    }
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

      {responseText && (
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
      )}
    </div>
  );
}

export default App;
