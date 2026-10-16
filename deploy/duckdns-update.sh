#!/usr/bin/env bash
# Point the DuckDNS name at this instance. DUCKDNS_DOMAIN and DUCKDNS_TOKEN come from the unit's
# EnvironmentFile. The token goes to curl through a config on stdin, so it never appears in the
# process list or in the journal.
set -euo pipefail

: "${DUCKDNS_DOMAIN:?DUCKDNS_DOMAIN is not set}"
: "${DUCKDNS_TOKEN:?DUCKDNS_TOKEN is not set}"
if [ "$DUCKDNS_TOKEN" = "CHANGE_ME" ]; then
    echo "DuckDNS token not configured; skipping" >&2
    exit 0
fi

reply="$(curl -fsS --max-time 20 -K - <<EOF
get
url = "https://www.duckdns.org/update"
data-urlencode = "domains=${DUCKDNS_DOMAIN}"
data-urlencode = "token=${DUCKDNS_TOKEN}"
data-urlencode = "ip="
EOF
)"
if [ "$reply" != "OK" ]; then
    echo "DuckDNS update failed (reply: ${reply})" >&2
    exit 1
fi
