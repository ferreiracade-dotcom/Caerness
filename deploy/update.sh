#!/usr/bin/env bash
# Update a running installation: pull, install dependencies, run the smoke tests as the service
# user against a throwaway campaign directory, and only then restart. Any failing step stops here.
#   sudo /opt/caerness/deploy/update.sh
set -euo pipefail

APP=/opt/caerness
PY="$APP/.venv/bin/python"

if [ "$(id -u)" -ne 0 ]; then
    echo "run as root (sudo)" >&2
    exit 1
fi

git -C "$APP" pull --ff-only
uv pip install --python "$PY" -r "$APP/connector/requirements.txt" numpy

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
chown caerness:caerness "$scratch"
for smoke in connector_http_test.py connector_oauth_test.py; do
    echo "== $smoke"
    runuser -u caerness -- env CAERNESS_CAMPAIGN_DIR="$scratch/campaigns" TMPDIR="$scratch" \
        PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$APP" "$PY" "$APP/tests/$smoke"
done

systemctl restart caerness
sleep 3
curl -fsS http://127.0.0.1:8765/health
echo
