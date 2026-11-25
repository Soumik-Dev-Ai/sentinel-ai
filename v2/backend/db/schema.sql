-- Sentinel AI 2.0 — Turso (libSQL) Database Schema
-- Compatible with both standard SQLite (.db upload) and Turso/libSQL.

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    timestamp INTEGER NOT NULL,
    goal TEXT NOT NULL,
    success INTEGER NOT NULL,
    steps INTEGER NOT NULL DEFAULT 0,
    corrections INTEGER NOT NULL DEFAULT 0,
    elapsed REAL NOT NULL DEFAULT 0,
    provider TEXT NOT NULL DEFAULT '',
    tokens INTEGER NOT NULL DEFAULT 0,
    cost REAL NOT NULL DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON runs(timestamp DESC);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    goal TEXT NOT NULL,
    summary TEXT NOT NULL,
    error_signature TEXT,
    strategy TEXT,
    success INTEGER NOT NULL DEFAULT 1,
    created_ts REAL NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    embedding F32_BLOB(256)
);

CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);

-- Optional: run inside Turso Shell if memories grows beyond ~5,000 rows:
-- CREATE INDEX IF NOT EXISTS idx_memories_vec ON memories(libsql_vector_idx(embedding));
