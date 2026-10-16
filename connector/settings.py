"""Deployment settings, read from the environment in one place."""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REDIRECT_URIS = ("https://claude.ai/api/mcp/auth_callback",)
HARD_MAX_ADVANCE_DAYS = 30

# Every environment variable this module reads (deploy/caerness.env.example must list exactly these).
ENV_KEYS = (
    "CAERNESS_PUBLIC_URL",
    "CAERNESS_AUTH_DB",
    "CAERNESS_PASSPHRASE_HASH",
    "CAERNESS_REDIRECT_URIS",
    "CAERNESS_CAMPAIGN",
    "CAERNESS_MAX_ADVANCE_DAYS",
    "CAERNESS_BACKUP_DIR",
)


def parse_max_advance_days(raw: str | None) -> int:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return HARD_MAX_ADVANCE_DAYS
    return max(1, min(HARD_MAX_ADVANCE_DAYS, value))


@dataclass(frozen=True)
class Settings:
    public_url: str | None = None
    auth_db_path: Path = Path("auth.db")
    passphrase_hash: str | None = None
    owner_redirect_uris: tuple[str, ...] = DEFAULT_REDIRECT_URIS
    campaign: str = "main"
    max_advance_days: int = HARD_MAX_ADVANCE_DAYS
    backup_dir: Path | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        def get(key: str) -> str | None:
            value = (env.get(key) or "").strip()
            return value or None

        public = get("CAERNESS_PUBLIC_URL")
        uris = tuple(u.strip() for u in (get("CAERNESS_REDIRECT_URIS") or "").split(",") if u.strip())
        backup = get("CAERNESS_BACKUP_DIR")
        return cls(
            public_url=public.rstrip("/") if public else None,
            auth_db_path=Path(get("CAERNESS_AUTH_DB") or "auth.db"),
            passphrase_hash=get("CAERNESS_PASSPHRASE_HASH"),
            owner_redirect_uris=uris or DEFAULT_REDIRECT_URIS,
            campaign=get("CAERNESS_CAMPAIGN") or "main",
            max_advance_days=parse_max_advance_days(get("CAERNESS_MAX_ADVANCE_DAYS")),
            backup_dir=Path(backup) if backup else None,
        )
