"""Connector-owned tables: idempotent call log, GM notes, meta."""
from __future__ import annotations

from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def ensure_connector_schema(conn) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
