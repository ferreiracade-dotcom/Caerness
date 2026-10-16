"""Entry point: launched by the Claude desktop app (stdio, default) or by systemd (--transport http)."""
from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for stream in (sys.stdin, sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8")

from connector import server  # noqa: E402


def serve_http(host: str, port: int) -> None:
    import uvicorn

    from connector.campaign import open_campaign
    from connector.http_app import build_app
    from connector.settings import Settings

    settings = Settings.from_env()
    with contextlib.redirect_stdout(sys.stderr):
        open_campaign(settings.campaign)
        app = build_app(settings)
    uvicorn.run(app, host=host, port=port, proxy_headers=True, forwarded_allow_ips="127.0.0.1")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Caerness connector")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if args.transport == "http":
        serve_http(args.host, args.port)
    else:
        server.main()


if __name__ == "__main__":
    main()
