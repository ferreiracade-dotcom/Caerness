from __future__ import annotations

import configparser
import importlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DEPLOY = ROOT / "deploy"


def unit(name: str) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read(DEPLOY / name, encoding="utf-8")
    return cp


def env_pairs(path: Path) -> dict[str, str]:
    pairs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            pairs[key.strip()] = value.strip()
    return pairs


def run():
    from connector.settings import ENV_KEYS

    names = ["caerness.service", "caerness-backup.service", "caerness-backup.timer", "Caddyfile",
             "caerness.env.example", "host.env.example", "install.sh", "update.sh", "duckdns-update.sh",
             "duckdns.service", "duckdns.timer", "caddy-override.conf"]
    for n in names:
        assert (DEPLOY / n).is_file(), f"missing deploy/{n}"

    svc = unit("caerness.service")
    start = svc["Service"]["ExecStart"]
    assert "connector/run_server.py" in start and "--transport http" in start, start
    port = re.search(r"--port\s+(\d+)", start)
    assert port and "--host 127.0.0.1" in start, start
    s = svc["Service"]
    assert s["User"] == "caerness" and s["EnvironmentFile"] == "/etc/caerness/caerness.env"
    assert s["Restart"] == "always" and s["NoNewPrivileges"] == "yes" and s["ProtectSystem"] == "strict"
    assert s["ReadWritePaths"] == "/var/lib/caerness" and s["ProtectHome"] == "yes" and s["PrivateTmp"] == "yes"
    assert int(s["TimeoutStopSec"]) >= 120
    for unit_name in ("caerness.service", "caerness-backup.service"):  # repeated Environment= keys: read the raw text
        assert "Environment=CAERNESS_CAMPAIGN_DIR=/var/lib/caerness/campaigns" in (DEPLOY / unit_name).read_text(encoding="utf-8")

    caddy = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
    upstream = re.search(r"reverse_proxy\s+127\.0\.0\.1:(\d+)", caddy)
    assert upstream and upstream.group(1) == port.group(1), (upstream and upstream.group(1), port.group(1))
    assert "{$CAERNESS_HOST}" in caddy and "flush_interval -1" in caddy
    assert re.search(r"max_size\s+1MB", caddy) and "X-Content-Type-Options" in caddy

    # Environment files: exactly the keys Settings reads; placeholders only.
    example = env_pairs(DEPLOY / "caerness.env.example")
    assert set(example) == set(ENV_KEYS), set(example) ^ set(ENV_KEYS)
    text = (DEPLOY / "caerness.env.example").read_text(encoding="utf-8")
    assert re.search(r"(?i)mode\s*0?640", text) and "root:caerness" in text
    assert "scrypt$" not in text
    assert example["CAERNESS_PASSPHRASE_HASH"] in ("", "CHANGE_ME")
    assert example["CAERNESS_PUBLIC_URL"].startswith("https://YOUR-")
    host = env_pairs(DEPLOY / "host.env.example")
    assert set(host) == {"CAERNESS_HOST", "DUCKDNS_DOMAIN", "DUCKDNS_TOKEN"}, host
    assert host["DUCKDNS_TOKEN"] in ("", "CHANGE_ME") and re.search(r"(?i)mode\s*0?600", (DEPLOY / "host.env.example").read_text())

    # Backup units.
    bsvc = unit("caerness-backup.service")["Service"]
    assert bsvc["Type"] == "oneshot" and bsvc["User"] == "caerness"
    assert bsvc["EnvironmentFile"] == "/etc/caerness/caerness.env"
    m = re.search(r"-m (connector\.backup)\b.*--campaign \$\{CAERNESS_CAMPAIGN\}.*--label daily", bsvc["ExecStart"])
    assert m, bsvc["ExecStart"]
    importlib.import_module(m.group(1))
    timer = unit("caerness-backup.timer")
    assert timer["Timer"]["OnCalendar"] == "*-*-* 04:30:00 UTC" and timer["Timer"]["Persistent"] == "true"
    assert timer["Install"]["WantedBy"] == "timers.target"

    dsvc, dtimer = unit("duckdns.service")["Service"], unit("duckdns.timer")["Timer"]
    assert dsvc["EnvironmentFile"] == "/etc/caerness/host.env" and "duckdns-update.sh" in dsvc["ExecStart"]
    assert dtimer["OnUnitActiveSec"] and "/etc/caerness/host.env" in (DEPLOY / "caddy-override.conf").read_text()

    # Scripts: syntax, no embedded secrets, safe habits.
    bash = shutil.which("bash")
    for sh in sorted(DEPLOY.glob("*.sh")):
        body = sh.read_text(encoding="utf-8")
        assert body.startswith("#!/usr/bin/env bash\n") and "set -euo pipefail" in body, sh.name
        assert "\r" not in body, f"{sh.name} must use LF line endings"
        assert "scrypt$" not in body and not re.search(r"[A-Za-z0-9_\-]{40,}", body.replace("-", "")), sh.name
        assert not re.search(r"(?i)(token|passphrase|password)\s*=\s*['\"]?[A-Za-z0-9]{12,}", body), sh.name
        if bash:
            r = subprocess.run([bash, "-n", str(sh)], capture_output=True, text=True)
            assert r.returncode == 0, f"{sh.name}: {r.stderr}"
    install = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "iptables -S" in install and "caerness.env" in install and "unattended" in install
    assert 'if [ ! -e "$ETC/caerness.env" ]' in install and 'if [ ! -e "$ETC/host.env" ]' in install  # never overwrites
    assert "ETC=/etc/caerness" in install
    update = (DEPLOY / "update.sh").read_text(encoding="utf-8")
    assert update.index("connector_oauth_test.py") < update.index("systemctl restart caerness")
    assert "--ff-only" in update and "/health" in update
    duck = (DEPLOY / "duckdns-update.sh").read_text(encoding="utf-8")
    assert "-K -" in duck and "token=" in duck and "--data-urlencode token" not in duck  # token only via stdin config

    # Ignore rules and line endings.
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "deploy/*.env" in gitignore and "*.bak" in gitignore
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "deploy/" in attrs and "eol=lf" in attrs
    print("deploy_files_test passed")


if __name__ == "__main__":
    run()
