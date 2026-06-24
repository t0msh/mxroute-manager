#!/usr/bin/env bash
# Add an entry to SpamAssassin blacklist for a domain.
# Usage:
#   export MXM_URL=https://manager.example.com
#   export MXM_TOKEN=mxm_your_token
#   ./blacklist-sender.sh example.com karen@hr.example.com
set -euo pipefail

MANAGER_URL="${MXM_URL:-}"
TOKEN="${MXM_TOKEN:-}"
DOMAIN="${1:?domain required}"
ENTRY="${2:?entry required (e.g. karen@hr.example.com)}"

if [[ -z "$MANAGER_URL" || -z "$TOKEN" ]]; then
  echo "Set MXM_URL and MXM_TOKEN" >&2
  exit 1
fi

MANAGER_URL="${MANAGER_URL%/}"
URI="$MANAGER_URL/api/domains/$DOMAIN/spam/blacklist"
PAYLOAD=$(ENTRY="$ENTRY" python3 - <<'PY'
import json, os
print(json.dumps({"entry": os.environ["ENTRY"]}))
PY
)

echo "Blacklisting '$ENTRY' on $DOMAIN ..."
curl -sS -f -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  "$URI"
echo
echo "Done."
