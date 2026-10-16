"""Create/open a campaign copy and optionally set its protagonist.

Usage: python connector/setup_campaign.py --campaign NAME [--actor "Full Name"]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--actor", default="")
    a = ap.parse_args()
    from connector.campaign import connect_campaign, open_campaign
    from engine.player import get_player, set_player

    path = open_campaign(a.campaign)
    print(f"campaign: {path}", file=sys.stderr)
    with connect_campaign() as conn:
        if a.actor:
            rows = conn.execute("SELECT id,name FROM actors WHERE name=?", (a.actor,)).fetchall()
            if len(rows) != 1:
                raise SystemExit(f"expected exactly one actor named {a.actor!r}, found {len(rows)}")
            set_player(conn, int(rows[0]["id"]), campaign_name=a.campaign)
            conn.commit()
        p = get_player(conn)
        print(f"protagonist: {p['actor_name'] if p else '(none)'}", file=sys.stderr)


if __name__ == "__main__":
    main()
