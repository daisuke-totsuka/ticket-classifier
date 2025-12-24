import json
import math
import os
import re
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
import google.generativeai as genai

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "gemini_responses.db"
EMBEDDING_MODEL = os.environ.get("GEMINI_EMBEDDING_MODEL", "models/text-embedding-004")
MIN_SIMILARITY = 0.93

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not API_KEY:
    raise RuntimeError("Gemini APIキーが設定されていません。")

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")


def _strip_code_fences(text: str) -> str:
    """Remove Markdown code fences if Gemini wraps the JSON response."""
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return text


def _extract_json_payload(text: str) -> dict:
    """Try to parse JSON out of Gemini's response."""
    cleaned = _strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start != -1 and end != -1 and end > start:
            fragment = cleaned[start : end + 1]
            return json.loads(fragment)
        raise


def _coerce_confidence(value):
    """Convert confidence-like values to float when possible."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
            if match:
                try:
                    return float(match.group())
                except ValueError:
                    return None
    return None


def _format_payload_for_humans(payload: dict) -> tuple[str, list[dict[str, str]], float | None]:
    """Build a human-friendly view from the Gemini JSON payload."""
    field_labels = {
        "ticket_classification_title": "分類タイトル",
        "ticket_classification_content": "分類内容",
        "gemini_confidence": "Gemini信頼度",
        "gemini_answer": "Geminiの提案内容",
    }

    segments: list[dict[str, str]] = []
    confidence_value = None

    for key, label in field_labels.items():
        if key not in payload:
            continue
        value = payload[key]
        if value is None:
            continue

        if key == "gemini_confidence":
            parsed_confidence = _coerce_confidence(value)
            if parsed_confidence is not None:
                confidence_value = parsed_confidence

        if isinstance(value, float):
            value_str = f"{value:.2f}"
        elif isinstance(value, (list, dict)):
            value_str = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            value_str = str(value).strip()
        segments.append({"label": label, "value": value_str})

    for key, value in payload.items():
        if key in field_labels:
            continue
        value_str = json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (list, dict)) else str(value).strip()
        segments.append({"label": key, "value": value_str})

    formatted = "\n\n".join(f"{segment['label']}:\n{segment['value']}" for segment in segments if segment["value"])
    return formatted, segments, confidence_value


def _generate_embedding(text: str) -> list[float] | None:
    """Create an embedding vector for the provided text using Gemini's embedding API."""
    content = (text or "").strip()
    if not content:
        return None
    try:
        response = genai.embed_content(model=EMBEDDING_MODEL, content=content)
    except Exception as exc:  # pragma: no cover - network/API failure
        app.logger.warning("Failed to generate embedding: %s", exc)
        return None

    if isinstance(response, dict):
        vector = response.get("embedding")
        if vector is None and "data" in response:
            data = response.get("data") or []
            if data and isinstance(data[0], dict):
                vector = data[0].get("embedding")
    else:
        vector = getattr(response, "embedding", None)

    if not vector:
        app.logger.warning("Embedding response missing vector: %s", response)
        return None

    return [float(x) for x in vector]


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _search_similar(query_embedding: list[float], top_k: int | None = 5) -> list[dict]:
    """Return the most similar stored responses based on cosine similarity."""
    if not query_embedding:
        return []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, ticket, raw_response, parsed_json, confidence, created_at, embedding
            FROM gemini_responses
            WHERE embedding IS NOT NULL
            """
        ).fetchall()

    candidates: list[dict] = []
    for row in rows:
        try:
            stored_vector = json.loads(row["embedding"])
        except (TypeError, json.JSONDecodeError):
            continue
        similarity = _cosine_similarity(query_embedding, stored_vector)
        parsed_json = row["parsed_json"]
        parsed = None
        if parsed_json:
            try:
                parsed = json.loads(parsed_json)
            except json.JSONDecodeError:
                parsed = None
        candidates.append(
            {
                "id": row["id"],
                "ticket": row["ticket"],
                "raw_response": row["raw_response"],
                "parsed": parsed,
                "confidence": row["confidence"],
                "created_at": row["created_at"],
                "similarity": similarity,
            }
        )

    candidates.sort(key=lambda item: item["similarity"], reverse=True)
    filtered = [item for item in candidates if item["similarity"] >= MIN_SIMILARITY]
    if top_k is None:
        return filtered
    return filtered[:top_k]


def _init_db() -> None:
    """Create persistent storage for Gemini responses when needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gemini_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket TEXT NOT NULL,
                raw_response TEXT NOT NULL,
                parsed_json TEXT,
                confidence REAL,
                embedding TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(gemini_responses)")}
        if "embedding" not in columns:
            conn.execute("ALTER TABLE gemini_responses ADD COLUMN embedding TEXT")
        conn.commit()


def _persist_response(
    ticket: str,
    raw_response: str,
    payload: dict,
    confidence: float | None,
    embedding: list[float] | None,
) -> None:
    """Insert Gemini API payload into SQLite, logging errors without interrupting the request."""
    serialized_payload = json.dumps(payload, ensure_ascii=False)
    serialized_embedding = json.dumps(embedding) if embedding else None
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO gemini_responses (ticket, raw_response, parsed_json, confidence, embedding)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ticket, raw_response, serialized_payload, confidence, serialized_embedding),
            )
            conn.commit()
    except Exception as exc:  # pragma: no cover - persistence failures shouldn't break the API
        app.logger.warning("Failed to persist Gemini response: %s", exc)


_init_db()



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
        "以下のチケット内容を分析してください。出力は必ず次のJSON形式で返してください。\n"
        "{\n"
        '  "ticket_classification_title": "短いタイトル",\n'
        '  "ticket_classification_content": "分類の説明",\n'
        '  "gemini_confidence": 0.0,\n'
        '  "gemini_answer": "Geminiの提案内容"\n'
        "}\n"
        "各フィールドは日本語で記載し、gemini_confidenceは0から1の間の数値で小数点以下2桁程度にしてください。\n"
        "チケット内容:\n"
        f"{ticket}"
    )

    try:
        response = model.generate_content(prompt)
    except Exception as exc:  # pragma: no cover - API呼び出し時の例外
        return jsonify({"error": f"Gemini API呼び出しに失敗しました: {exc}"}), 502

    text = (getattr(response, "text", None) or "").strip()

    if not text:
        return jsonify({"error": "Geminiの応答が空でした", "raw": text}), 502

    try:
        payload = _extract_json_payload(text)
    except json.JSONDecodeError:
        return jsonify({"error": "Geminiの応答をJSONとして解釈できませんでした", "raw": text}), 502

    formatted_text, segments, confidence = _format_payload_for_humans(payload)

    embedding_input = "\n\n".join(
        [
            "ticket:",
            ticket,
            "response:",
            formatted_text or text,
        ]
    )
    embedding_vector = _generate_embedding(embedding_input)

    similar_matches: list[dict] = []
    if embedding_vector:
        similar_matches = _search_similar(embedding_vector, top_k=None)

    _persist_response(
        ticket=ticket,
        raw_response=text,
        payload=payload,
        confidence=confidence,
        embedding=embedding_vector,
    )

    return jsonify({
        "raw": text,
        "raw_response": text,
        "parsed": payload,
        "segments": segments,
        "result": formatted_text or text,
        "confidence": confidence if confidence is not None else _coerce_confidence(payload.get("gemini_confidence")),
        "matches": similar_matches,
        "similarity_threshold": MIN_SIMILARITY,
    }), 200


@app.route("/api/search", methods=["POST"])
def search() -> tuple:
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or data.get("text") or "").strip()
    if not query:
        return jsonify({"error": "queryが指定されていません"}), 400

    top_k_raw = data.get("top_k")
    try:
        top_k = int(top_k_raw) if top_k_raw is not None else 5
    except (TypeError, ValueError):
        top_k = 5
    top_k = max(1, min(top_k, 20))

    embedding = _generate_embedding(query)
    if embedding is None:
        return jsonify({"error": "埋め込みの生成に失敗しました"}), 502

    matches = _search_similar(embedding, top_k=top_k)
    return jsonify({"query": query, "top_k": top_k, "results": matches}), 200


@app.route("/api/responses", methods=["GET"])
def list_responses() -> tuple:
    limit_raw = request.args.get("limit")
    offset_raw = request.args.get("offset")
    try:
        limit = int(limit_raw) if limit_raw is not None else 50
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 200))

    try:
        offset = int(offset_raw) if offset_raw is not None else 0
    except (TypeError, ValueError):
        offset = 0
    offset = max(0, offset)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, ticket, raw_response, parsed_json, confidence, created_at
            FROM gemini_responses
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

    items = []
    for row in rows:
        parsed = None
        if row["parsed_json"]:
            try:
                parsed = json.loads(row["parsed_json"])
            except json.JSONDecodeError:
                parsed = None
        items.append(
            {
                "id": row["id"],
                "ticket": row["ticket"],
                "raw_response": row["raw_response"],
                "parsed": parsed,
                "confidence": row["confidence"],
                "created_at": row["created_at"],
            }
        )

    return jsonify({"items": items, "limit": limit, "offset": offset, "count": len(items)}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
