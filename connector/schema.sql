CREATE TABLE IF NOT EXISTS connector_calls (
    call_id TEXT PRIMARY KEY,
    tool TEXT NOT NULL,
    request_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    world_day INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gm_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_kind TEXT NOT NULL CHECK (subject_kind IN ('actor','location','general')),
    subject_id INTEGER,
    text TEXT NOT NULL,
    provenance TEXT NOT NULL DEFAULT 'gm_improvised',
    world_day INTEGER NOT NULL,
    call_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gm_notes_subject ON gm_notes(subject_kind, subject_id);

CREATE TABLE IF NOT EXISTS connector_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
