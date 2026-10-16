"""SQLite persistence for the single-owner OAuth server (separate file from any campaign).

Secrets (authorization codes, access and refresh tokens, pending login handles) are stored only as
SHA-256 digests. One short-lived connection per call; WAL; the file is created mode 600 on POSIX.
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients(
    client_id TEXT PRIMARY KEY, client_json TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pending(
    req_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, params_json TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS codes(
    code_hash TEXT PRIMARY KEY, payload_json TEXT NOT NULL, expires_at REAL NOT NULL,
    used INTEGER NOT NULL DEFAULT 0, family_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tokens(
    token_hash TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('access','refresh')),
    client_id TEXT NOT NULL, scopes TEXT NOT NULL, expires_at REAL NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0, rotated INTEGER NOT NULL DEFAULT 0, family_id TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS tokens_family ON tokens(family_id);
CREATE TABLE IF NOT EXISTS login_attempts(ts REAL NOT NULL, ip TEXT);
"""


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class AuthStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextlib.contextmanager
    def _db(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # commit or roll back
                yield conn
        finally:
            conn.close()

    def ensure_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)  # owner-only before SQLite touches it
            os.close(fd)
        with contextlib.suppress(OSError):
            if os.name == "posix":
                os.chmod(self.path, 0o600)
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
        with self._db() as db:
            db.executescript(SCHEMA)

    # clients ---------------------------------------------------------------------------------
    def put_client(self, client_id: str, client_json: str, created_at: float) -> None:
        with self._db() as db:
            db.execute("INSERT INTO clients(client_id,client_json,created_at) VALUES (?,?,?)",
                       (client_id, client_json, created_at))

    def get_client_json(self, client_id: str) -> str | None:
        with self._db() as db:
            row = db.execute("SELECT client_json FROM clients WHERE client_id=?", (client_id,)).fetchone()
        return row["client_json"] if row else None

    def count_clients(self) -> int:
        with self._db() as db:
            return int(db.execute("SELECT COUNT(*) FROM clients").fetchone()[0])

    def prune_unused_clients(self, older_than: float) -> int:
        """Drop registrations that never obtained a token and are old (open registration is public)."""
        with self._db() as db:
            cur = db.execute(
                "DELETE FROM clients WHERE created_at<? AND client_id NOT IN (SELECT client_id FROM tokens)"
                " AND client_id NOT IN (SELECT client_id FROM pending)", (older_than,))
            return cur.rowcount

    # pending authorizations ---------------------------------------------------------------------
    def put_pending(self, req_id: str, client_id: str, params_json: str, expires_at: float) -> None:
        with self._db() as db:
            db.execute("INSERT INTO pending(req_hash,client_id,params_json,expires_at) VALUES (?,?,?,?)",
                       (digest(req_id), client_id, params_json, expires_at))

    def get_pending(self, req_id: str, now: float) -> sqlite3.Row | None:
        with self._db() as db:
            db.execute("DELETE FROM pending WHERE expires_at<?", (now,))
            return db.execute("SELECT client_id, params_json, expires_at FROM pending WHERE req_hash=? AND expires_at>=?",
                              (digest(req_id), now)).fetchone()

    def take_pending(self, req_id: str, now: float) -> sqlite3.Row | None:
        """Atomically consume a pending request (single use)."""
        with self._db() as db:
            row = db.execute("SELECT client_id, params_json FROM pending WHERE req_hash=? AND expires_at>=?",
                             (digest(req_id), now)).fetchone()
            if row is None:
                return None
            gone = db.execute("DELETE FROM pending WHERE req_hash=?", (digest(req_id),)).rowcount
        return row if gone == 1 else None

    # authorization codes --------------------------------------------------------------------------
    def put_code(self, code: str, payload_json: str, expires_at: float, family_id: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM codes WHERE expires_at<? AND used=0", (expires_at - 86400,))
            db.execute("INSERT INTO codes(code_hash,payload_json,expires_at,used,family_id) VALUES (?,?,?,0,?)",
                       (digest(code), payload_json, expires_at, family_id))

    def get_code(self, code: str) -> sqlite3.Row | None:
        with self._db() as db:
            return db.execute("SELECT payload_json, expires_at, used, family_id FROM codes WHERE code_hash=?",
                              (digest(code),)).fetchone()

    def use_code(self, code: str) -> bool:
        with self._db() as db:
            return db.execute("UPDATE codes SET used=1 WHERE code_hash=? AND used=0", (digest(code),)).rowcount == 1

    # tokens -----------------------------------------------------------------------------------------
    def put_token(self, token: str, kind: str, client_id: str, scopes: str, expires_at: float, family_id: str) -> None:
        with self._db() as db:
            db.execute("INSERT INTO tokens(token_hash,kind,client_id,scopes,expires_at,family_id) VALUES (?,?,?,?,?,?)",
                       (digest(token), kind, client_id, scopes, expires_at, family_id))

    def get_token(self, token: str) -> sqlite3.Row | None:
        with self._db() as db:
            return db.execute(
                "SELECT kind, client_id, scopes, expires_at, revoked, rotated, family_id FROM tokens WHERE token_hash=?",
                (digest(token),)).fetchone()

    def rotate_refresh(self, token: str, client_id: str) -> bool:
        """Mark a live refresh token as used; False if it was already rotated, revoked or not this client's."""
        with self._db() as db:
            return db.execute(
                "UPDATE tokens SET rotated=1 WHERE token_hash=? AND kind='refresh' AND client_id=? AND rotated=0 AND revoked=0",
                (digest(token), client_id)).rowcount == 1

    def revoke_family(self, family_id: str) -> None:
        with self._db() as db:
            db.execute("UPDATE tokens SET revoked=1 WHERE family_id=?", (family_id,))

    def prune_tokens(self, now: float) -> None:
        with self._db() as db:
            db.execute("DELETE FROM tokens WHERE expires_at<?", (now - 86400,))

    # login throttle --------------------------------------------------------------------------------------
    def add_login_failure(self, ts: float, ip: str | None) -> None:
        with self._db() as db:
            db.execute("INSERT INTO login_attempts(ts,ip) VALUES (?,?)", (ts, ip))

    def count_login_failures(self, since: float) -> int:
        with self._db() as db:
            db.execute("DELETE FROM login_attempts WHERE ts<?", (since - 86400,))
            return int(db.execute("SELECT COUNT(*) FROM login_attempts WHERE ts>=?", (since,)).fetchone()[0])
