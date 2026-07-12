"""Embedding cache backed by SQLite — avoids redundant API calls for identical texts."""

import hashlib
import json

from ..database import connect


def text_hash(text: str, model: str) -> str:
    """SHA-256 hash of model + text, used as cache key."""
    return hashlib.sha256(f"{model}:{text}".encode()).hexdigest()


def get_cached(hashes: list[str]) -> dict[str, list[float]]:
    """Return cached embeddings keyed by hash. Uncached hashes are absent from result."""
    if not hashes:
        return {}
    conn = connect()
    try:
        placeholders = ",".join(["?"] * len(hashes))
        rows = conn.execute(
            f"SELECT text_hash, embedding_json FROM embedding_cache "
            f"WHERE text_hash IN ({placeholders})",
            hashes,
        ).fetchall()
        return {row["text_hash"]: json.loads(row["embedding_json"]) for row in rows}
    finally:
        conn.close()


def save(entries: list[tuple[str, list[float], str]]) -> None:
    """Persist embeddings: [(text_hash, embedding, model), ...]."""
    if not entries:
        return
    conn = connect()
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO embedding_cache (text_hash, embedding_json, model) "
            "VALUES (?, ?, ?)",
            [(h, json.dumps(emb), model) for h, emb, model in entries],
        )
        conn.commit()
    finally:
        conn.close()
