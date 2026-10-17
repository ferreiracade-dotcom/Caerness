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

-- Continuity across chats (spec §8): reminders, never sources of truth.
CREATE TABLE IF NOT EXISTS campaign_recaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    world_day INTEGER NOT NULL,
    text TEXT NOT NULL,
    threads_json TEXT NOT NULL DEFAULT '[]',
    call_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS standing_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    world_day INTEGER NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
    call_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS character_sheet (
    field TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    world_day INTEGER NOT NULL,
    call_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS error_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    world_day INTEGER NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','fixed','declined')),
    call_id TEXT NOT NULL
);

-- What the GM made real through `author` (provenance only; the engine rows are the truth).
CREATE TABLE IF NOT EXISTS authored_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    entity_table TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    world_day INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_authored_entity ON authored_entities(entity_table, entity_id);
