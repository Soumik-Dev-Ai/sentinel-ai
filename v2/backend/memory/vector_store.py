"""Lightweight FAISS-backed vector store for Sentinel AI 2.0 persistent memory.

We embed memories with a deterministic hash-based bag-of-vectors fallback so
that the store works even without internet access to an embedding API, but
upgrade transparently to a stronger embedder if OpenAI is available.

Two collections:
  - "solved" — summaries of successfully-solved goals/subtasks.
  - "errors" — encountered errors together with the strategy that fixed them.

Codex loads the memories via `query_closest()` before each LLM call so the
coder preamble ("Past learnings:") is grounded in actual experience.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

import numpy as np

try:
    import faiss  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - import-time fallback only
    faiss = None  # type: ignore[assignment]


# -----------------------------------------------------------------------------
# Embedding (works with or without network)
# -----------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|[^\sA-Za-z0-9_]")
_EMBED_DIM = 256


def _hash_token(token: str) -> int:
    h = hashlib.blake2b(token.lower().encode("utf-8"), digest_size=4)
    return int.from_bytes(h.digest(), "big")


def _local_embed(text: str, dim: int = _EMBED_DIM) -> np.ndarray:
    """Deterministic locally-computed embedding.

    Combines a hashed bag-of-words (helps distinct vocabulary go to distinct
    bins) with a hash-trick bigram component to preserve a tiny bit of order
    information.  Normalized to unit L2 so cosine similarity = inner product.
    """
    tokens = _TOKEN_RE.findall(text)
    vec = np.zeros(dim, dtype=np.float32)
    for tok in tokens:
        vec[_hash_token(tok) % dim] += 1.0
    for a, b in zip(tokens, tokens[1:]):
        bigram = f"{a} {b}"
        vec[_hash_token(bigram) % dim] += 0.4
    n = float(np.linalg.norm(vec))
    if n == 0.0:
        return vec
    return vec / n


async def _openai_embed(texts: list[str]) -> Optional[list[np.ndarray]]:
    """Try OpenAI embeddings — returns None if unavailable or unauthorized."""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None
    try:
        import openai  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        client = openai.OpenAI(api_key=api_key)
        resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
        return [
            np.asarray(v.embedding, dtype=np.float32) for v in resp.data
        ]
    except Exception:
        return None


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a batch — uses OpenAI if available, otherwise local hash-trick."""
    if not texts:
        return np.zeros((0, _EMBED_DIM), dtype=np.float32)
    # Try OpenAI (synchronous wrapper — this module is called from background threads).
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            maybe = loop.run_until_complete(_openai_embed(texts))
        finally:
            loop.close()
        if maybe is not None and len(maybe) == len(texts):
            mat = np.vstack(maybe).astype(np.float32)
            # Normalize regardless of provider so cosine == dot.
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            return (mat / norms).astype(np.float32)
    except Exception:
        pass
    return np.vstack([_local_embed(t) for t in texts]).astype(np.float32)


def embed_text(text: str) -> np.ndarray:
    return embed_texts([text])[0]


# -----------------------------------------------------------------------------
# Memory entries
# -----------------------------------------------------------------------------

@dataclass
class MemoryEntry:
    """One stored memory row.

    `kind` is either "solved" or "error". For errors, `strategy` is the
    human-readable correction that fixed it (free text — the coder agent
    can read it as guidance).
    """
    id: str
    kind: str
    goal: str
    summary: str
    error_signature: Optional[str] = None
    strategy: Optional[str] = None
    success: bool = True
    created_ts: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------------
# Vector Store
# -----------------------------------------------------------------------------

_MEMORIES_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    goal TEXT NOT NULL,
    summary TEXT NOT NULL,
    error_signature TEXT,
    strategy TEXT,
    success INTEGER NOT NULL DEFAULT 1,
    created_ts REAL NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{{}}',
    embedding F32_BLOB({_EMBED_DIM})
)
"""


class VectorStore:
    """Persistent FAISS + Turso libSQL (or pure-numpy fallback) vector store.

    Thread-safe. Syncs with Turso when TURSO_DATABASE_URL + TURSO_AUTH_TOKEN are set
    and persist_dir is provided; falls back cleanly to local disk / FAISS / numpy.
    """

    def __init__(self, persist_dir: Optional[Path] = None, dim: int = _EMBED_DIM):
        self._lock = threading.RLock()
        self._dim = dim
        self._persist_dir = Path(persist_dir) if persist_dir else None
        if self._persist_dir:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._turso_ready = False
        self._entries: list[MemoryEntry] = []
        self._vectors: np.ndarray = np.zeros((0, dim), dtype=np.float32)
        self._index: Any = None  # faiss.IndexFlatIP | None
        if faiss is not None:
            self._index = faiss.IndexFlatIP(dim)
        self._load()
        self._rebuild_index()

    # ---------------- Persistence ----------------

    def _ensure_turso(self) -> bool:
        if self._persist_dir is None:
            return False
        from backend.db import turso
        if not turso.is_configured():
            return False
        if not self._turso_ready:
            turso.execute(_MEMORIES_SCHEMA)
            self._turso_ready = True
        return True

    def _entries_path(self) -> Optional[Path]:
        if self._persist_dir is None:
            return None
        return self._persist_dir / "memories.json"

    def _load(self) -> None:
        try:
            if self._ensure_turso():
                from backend.db import turso
                rows = turso.execute(
                    "SELECT id, kind, goal, summary, error_signature, strategy, success, created_ts, metadata "
                    "FROM memories ORDER BY created_ts ASC"
                )
                self._entries = [
                    MemoryEntry(
                        id=r["id"],
                        kind=r["kind"],
                        goal=r["goal"],
                        summary=r["summary"],
                        error_signature=r.get("error_signature"),
                        strategy=r.get("strategy"),
                        success=bool(r.get("success", 1)),
                        created_ts=float(r.get("created_ts") or 0.0),
                        metadata=json.loads(r.get("metadata") or "{}"),
                    )
                    for r in rows
                ]
                return
        except Exception:
            pass

        path = self._entries_path()
        if path is None or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for row in data.get("entries", []):
                self._entries.append(MemoryEntry(**row))
        except Exception:
            # Corrupt file — start empty rather than crashing.
            self._entries = []

    def _persist(self) -> None:
        path = self._entries_path()
        if path is None:
            return
        try:
            path.write_text(
                json.dumps(
                    {"entries": [e.to_dict() for e in self._entries]},
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        except Exception:
            # best-effort; do not raise
            pass

    def _rebuild_index(self) -> None:
        if not self._entries:
            self._vectors = np.zeros((0, self._dim), dtype=np.float32)
            if self._index is not None and faiss is not None:
                self._index.reset()
            return
        texts = [self._entry_text(e) for e in self._entries]
        self._vectors = embed_texts(texts)
        if self._index is not None and faiss is not None:
            self._index.reset()
            if len(self._vectors) > 0:
                self._index.add(self._vectors)  # type: ignore[arg-type]

    @staticmethod
    def _entry_text(e: MemoryEntry) -> str:
        parts = [e.goal, e.summary]
        if e.error_signature:
            parts.append(e.error_signature)
        if e.strategy:
            parts.append(e.strategy)
        return " ".join(p for p in parts if p)

    # ---------------- Public API ----------------

    def add(
        self,
        kind: str,
        goal: str,
        summary: str,
        error_signature: Optional[str] = None,
        strategy: Optional[str] = None,
        success: bool = True,
        metadata: Optional[dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Insert a memory and persist."""
        import time as _t
        with self._lock:
            entry_id = hashlib.sha1(
                f"{kind}|{goal}|{summary}|{error_signature}|{strategy}".encode("utf-8")
            ).hexdigest()[:16]
            # Avoid exact duplicate inserts.
            for existing in self._entries:
                if existing.id == entry_id:
                    return existing
            entry = MemoryEntry(
                id=entry_id,
                kind=kind,
                goal=goal,
                summary=summary,
                error_signature=error_signature,
                strategy=strategy,
                success=success,
                created_ts=_t.time(),
                metadata=metadata or {},
            )
            self._entries.append(entry)
            vec = embed_text(self._entry_text(entry)).reshape(1, -1)
            if self._vectors.shape[0] == 0:
                self._vectors = vec
            else:
                self._vectors = np.vstack([self._vectors, vec])
            if self._index is not None and faiss is not None and vec.shape[0] > 0:
                self._index.add(vec)  # type: ignore[arg-type]
            self._persist()
            try:
                if self._ensure_turso():
                    from backend.db import turso
                    emb = (
                        vec.reshape(-1)
                        if vec.shape[1] == self._dim
                        else _local_embed(self._entry_text(entry), self._dim)
                    )
                    turso.execute(
                        "INSERT OR IGNORE INTO memories "
                        "(id, kind, goal, summary, error_signature, strategy, success, created_ts, metadata, embedding) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, vector32(?))",
                        [
                            entry.id,
                            entry.kind,
                            entry.goal,
                            entry.summary,
                            entry.error_signature,
                            entry.strategy,
                            int(entry.success),
                            entry.created_ts,
                            json.dumps(entry.metadata, default=str),
                            json.dumps([round(float(x), 6) for x in emb]),
                        ],
                    )
            except Exception:
                pass
            return entry

    def query_closest(
        self,
        query: str,
        k: int = 3,
        kind: Optional[str] = None,
        min_score: float = 0.05,
    ) -> list[tuple[MemoryEntry, float]]:
        """Return up to k (entry, similarity) tuples above min_score.

        `kind` filters by solved/errors (None means all).
        """
        with self._lock:
            try:
                if self._ensure_turso():
                    from backend.db import turso
                    qv_local = _local_embed(query, self._dim)
                    vec_json = json.dumps([round(float(x), 6) for x in qv_local])
                    if kind is not None:
                        rows = turso.execute(
                            "SELECT id, kind, goal, summary, error_signature, strategy, success, created_ts, metadata, "
                            "(1.0 - vector_distance_cos(embedding, vector32(?))) AS sim "
                            "FROM memories WHERE kind = ? AND embedding IS NOT NULL "
                            "ORDER BY sim DESC LIMIT ?",
                            [vec_json, kind, k],
                        )
                    else:
                        rows = turso.execute(
                            "SELECT id, kind, goal, summary, error_signature, strategy, success, created_ts, metadata, "
                            "(1.0 - vector_distance_cos(embedding, vector32(?))) AS sim "
                            "FROM memories WHERE embedding IS NOT NULL "
                            "ORDER BY sim DESC LIMIT ?",
                            [vec_json, k],
                        )
                    pairs = []
                    for r in rows:
                        sc = float(r.get("sim") or 0.0)
                        if sc < min_score:
                            continue
                        pairs.append((
                            MemoryEntry(
                                id=r["id"],
                                kind=r["kind"],
                                goal=r["goal"],
                                summary=r["summary"],
                                error_signature=r.get("error_signature"),
                                strategy=r.get("strategy"),
                                success=bool(r.get("success", 1)),
                                created_ts=float(r.get("created_ts") or 0.0),
                                metadata=json.loads(r.get("metadata") or "{}"),
                            ),
                            sc,
                        ))
                    return pairs
            except Exception:
                pass

            if not self._entries:
                return []
            qv = embed_text(query).reshape(1, -1)
            if self._index is not None and faiss is not None and self._index.ntotal > 0:
                k_eff = min(k * 4, int(self._index.ntotal))
                if k_eff <= 0:
                    return []
                scores, indices = self._index.search(qv, k_eff)  # type: ignore[attr-defined]
                pairs = []
                for sc, idx in zip(scores[0].tolist(), indices[0].tolist()):
                    if idx < 0 or sc < min_score:
                        continue
                    entry = self._entries[idx]
                    if kind is not None and entry.kind != kind:
                        continue
                    pairs.append((entry, float(sc)))
                # Re-sort after kind filter (FAISS already sorted by score).
                return pairs[:k]
            # Pure numpy brute-force fallback (cosine == inner product since L2-normed).
            if self._vectors.shape[0] == 0:
                return []
            sims = self._vectors @ qv.reshape(-1)
            order = np.argsort(-sims)
            pairs = []
            for idx in order.tolist():
                sc = float(sims[idx])
                if sc < min_score:
                    continue
                entry = self._entries[idx]
                if kind is not None and entry.kind != kind:
                    continue
                pairs.append((entry, sc))
                if len(pairs) >= k:
                    break
            return pairs

    def format_preamble_for_coder(
        self,
        query: str,
        max_entries: int = 4,
    ) -> str:
        """Return a human-readable preamble of relevant past learnings.

        Returns "None" if there are no relevant memories (the caller can choose
        to omit the section).
        """
        sols = self.query_closest(query, k=max_entries, kind="solved")
        errs = self.query_closest(query, k=max_entries, kind="error")
        if not sols and not errs:
            return ""
        lines: list[str] = []
        if sols:
            lines.append("Past solved goals (RAG retrieved):")
            for entry, sc in sols:
                lines.append(
                    f"  - (sim={sc:.2f}) goal={entry.goal!r}: {entry.summary}"
                )
        if errs:
            lines.append("Past error strategies (RAG retrieved):")
            for entry, sc in errs:
                sig = entry.error_signature or "<no traceback>"
                strat = entry.strategy or "<unknown>"
                lines.append(
                    f"  - (sim={sc:.2f}) when error matched {sig!r}, "
                    f"this strategy worked: {strat}"
                )
        return "\n".join(lines)

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def all_entries(self) -> list[MemoryEntry]:
        with self._lock:
            return list(self._entries)


# -----------------------------------------------------------------------------
# Error signature helper (used by retry strategy router)
# -----------------------------------------------------------------------------

def error_signature(traceback_text: str) -> str:
    """Return a normalized signature like `AssertionError@line12` for RAG."""
    # last line that looks like an exception.
    for line in reversed(traceback_text.splitlines()):
        s = line.strip()
        if not s:
            continue
        # match "ExceptionType: message" or pure "ExceptionType"
        m = re.match(r"^([A-Z]\w*(?:Error|Exception|Warning))\b", s)
        if m:
            return m.group(1)
        if "Error" in s or "Exception" in s:
            return s.split(":", 1)[0][:80]
    return "<unknown>"
