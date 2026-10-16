"""Export a campaign to one consistent file (laptop side, before uploading to the VM).

Usage: python tools/export_campaign.py --campaign ansel --out ansel-export.db
The source is never modified; SQLite's backup API includes WAL content even while the app is open.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def export(campaign: str, out: Path) -> dict:
    from connector import backup
    from connector.campaign import _NAME, campaign_dir

    if not _NAME.match(campaign):
        raise ValueError("campaign name must match [A-Za-z0-9_-]{1,40}")
    src = campaign_dir() / f"{campaign}.db"
    if not src.is_file():
        raise ValueError(f"no such campaign file: {src}")
    out = Path(out)
    if out.resolve() == src.resolve() or out.resolve().parent == campaign_dir().resolve() and out.suffix == ".db":
        raise ValueError("refusing to write the export into the campaigns folder")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    backup.copy_consistent(src, out)
    return {"path": str(out), "bytes": out.stat().st_size, "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    try:
        info = export(args.campaign, Path(args.out))
    except (ValueError, OSError, RuntimeError) as e:
        print(f"export failed: {e}", file=sys.stderr)
        return 1
    print(f"exported {info['path']}  {info['bytes']} bytes  sha256 {info['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
