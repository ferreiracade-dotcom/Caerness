#!/usr/bin/env bash
# Install the Caerness connector on Ubuntu 24.04 (Oracle Ampere A1 or AMD micro). Idempotent; run as root.
#   sudo deploy/install.sh HOST          e.g. caerness-k7q3m9.duckdns.org
# Optional environment: BRANCH (default master), REPO.
# Nothing secret is stored here: the DuckDNS token is prompted for, the passphrase hash is made by
# connector.set_passphrase, and both live only in /etc/caerness (never overwritten once present).
set -euo pipefail

HOST="${1:?usage: install.sh HOST   (for example caerness-k7q3m9.duckdns.org)}"
BRANCH="${BRANCH:-master}"
REPO="${REPO:-https://github.com/ferreiracade-dotcom/Caerness.git}"
APP=/opt/caerness
STATE=/var/lib/caerness
ETC=/etc/caerness
PYDIR=/opt/caerness-python

if [ "$(id -u)" -ne 0 ]; then
    echo "run as root (sudo)" >&2
    exit 1
fi
if ! [[ "$HOST" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$ ]]; then
    echo "HOST must be a lowercase DNS name, got: $HOST" >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "== packages"
apt-get update -y
apt-get install -y curl git gpg ca-certificates debian-keyring debian-archive-keyring apt-transport-https unattended-upgrades

echo "== caddy (apt repository from caddyserver.com/docs/install)"
if ! command -v caddy >/dev/null 2>&1; then
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' -o /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -y
    apt-get install -y caddy
fi

echo "== uv and Python 3.13"
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi
export UV_PYTHON_INSTALL_DIR="$PYDIR"
uv python install 3.13

echo "== service user and directories"
id caerness >/dev/null 2>&1 || useradd --system --home-dir "$STATE" --shell /usr/sbin/nologin caerness
install -d -o caerness -g caerness -m 750 "$STATE" "$STATE/campaigns" "$STATE/backups"
install -d -o root -g caerness -m 750 "$ETC"

echo "== code ($REPO, branch $BRANCH)"
if [ ! -d "$APP/.git" ]; then
    git clone --branch "$BRANCH" "$REPO" "$APP"
else
    git -C "$APP" fetch origin "$BRANCH"
    git -C "$APP" checkout "$BRANCH"
    git -C "$APP" pull --ff-only origin "$BRANCH"
fi

echo "== virtualenv and dependencies"
uv venv --python 3.13 --allow-existing "$APP/.venv"
uv pip install --python "$APP/.venv/bin/python" -r "$APP/connector/requirements.txt" numpy
"$APP/.venv/bin/python" -c "import sys, numpy, sqlite3; print(sys.version.split()[0], 'numpy', numpy.__version__, 'sqlite', sqlite3.sqlite_version)"

echo "== configuration (existing files are never overwritten)"
if [ ! -e "$ETC/caerness.env" ]; then
    install -o root -g caerness -m 640 "$APP/deploy/caerness.env.example" "$ETC/caerness.env"
    sed -i "s|^CAERNESS_PUBLIC_URL=.*|CAERNESS_PUBLIC_URL=https://${HOST}|" "$ETC/caerness.env"
fi
if [ ! -e "$ETC/host.env" ]; then
    install -o root -g root -m 600 "$APP/deploy/host.env.example" "$ETC/host.env"
    sed -i "s|^CAERNESS_HOST=.*|CAERNESS_HOST=${HOST}|; s|^DUCKDNS_DOMAIN=.*|DUCKDNS_DOMAIN=${HOST%%.*}|" "$ETC/host.env"
fi
if grep -q '^DUCKDNS_TOKEN=CHANGE_ME$' "$ETC/host.env" && [ -r /dev/tty ]; then
    read -r -s -p "DuckDNS token (hidden; press Enter to skip): " token </dev/tty || token=""
    echo
    if [[ "$token" =~ ^[0-9a-f-]{36}$ ]]; then
        sed -i "s|^DUCKDNS_TOKEN=.*|DUCKDNS_TOKEN=${token}|" "$ETC/host.env"
    elif [ -n "$token" ]; then
        echo "That does not look like a DuckDNS token (a 36-character UUID); skipped." >&2
    fi
    unset token
fi

echo "== units"
install -m 644 "$APP"/deploy/caerness.service "$APP"/deploy/caerness-backup.service "$APP"/deploy/caerness-backup.timer \
    "$APP"/deploy/duckdns.service "$APP"/deploy/duckdns.timer /etc/systemd/system/
install -d /etc/systemd/system/caddy.service.d
install -m 644 "$APP/deploy/caddy-override.conf" /etc/systemd/system/caddy.service.d/caerness.conf
install -m 644 "$APP/deploy/Caddyfile" /etc/caddy/Caddyfile
chmod 755 "$APP"/deploy/*.sh
systemctl daemon-reload

echo "== firewall (Oracle Ubuntu images ship restrictive iptables rules)"
for port in 80 443; do
    iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null \
        || iptables -I INPUT 1 -p tcp --dport "$port" -m conntrack --ctstate NEW -j ACCEPT
done
if command -v netfilter-persistent >/dev/null 2>&1; then
    netfilter-persistent save
else
    echo "netfilter-persistent not found: the rules above are not saved across reboots." >&2
fi
iptables -S INPUT
echo "(also open TCP 80 and 443 in the VCN security list; that is a console step)"

echo "== automatic security updates"
printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' > /etc/apt/apt.conf.d/20auto-upgrades

echo "== services"
systemctl enable --now caerness-backup.timer
if ! grep -q '^DUCKDNS_TOKEN=CHANGE_ME$' "$ETC/host.env"; then
    systemctl enable --now duckdns.timer
else
    echo "DuckDNS token not set: duckdns.timer not enabled (set DUCKDNS_TOKEN in $ETC/host.env, then: systemctl enable --now duckdns.timer)"
fi
systemctl enable caddy
systemctl restart caddy
systemctl enable caerness
if grep -q '^CAERNESS_PASSPHRASE_HASH=scrypt\$' "$ETC/caerness.env"; then
    systemctl restart caerness
    sleep 3
    curl -fsS http://127.0.0.1:8765/health && echo
else
    cat <<MSG
The connector is NOT started yet: no passphrase hash is configured. Next:
  sudo -u caerness $APP/.venv/bin/python -m connector.set_passphrase
  (paste the printed CAERNESS_PASSPHRASE_HASH=... line over the CHANGE_ME line in $ETC/caerness.env)
  sudo systemctl restart caerness
MSG
fi
systemctl --no-pager --lines=0 status caerness caddy || true
