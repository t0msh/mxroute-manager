#!/usr/bin/env bash
# Create a mailbox via MXroute Manager API.
# Usage:
#   export MXM_URL=https://manager.example.com
#   export MXM_TOKEN=mxm_your_token
#   ./deploy-mailbox.sh example.com alex 'Abcd1234!'
set -euo pipefail

MANAGER_URL="${MXM_URL:-}"
TOKEN="${MXM_TOKEN:-}"
DOMAIN="${1:?domain required}"
USERNAME="${2:?username required}"
PASSWORD="${3:?password required}"
QUOTA="${4:-1024}"
LIMIT="${5:-9600}"
RECOVERY_EMAIL="${6:-}"

if [[ -z "$MANAGER_URL" || -z "$TOKEN" ]]; then
  echo "Set MXM_URL and MXM_TOKEN" >&2
  exit 1
fi

MANAGER_URL="${MANAGER_URL%/}"
URI="$MANAGER_URL/api/domains/$DOMAIN/email-accounts"

PAYLOAD=$(DOMAIN="$DOMAIN" USERNAME="$USERNAME" PASSWORD="$PASSWORD" QUOTA="$QUOTA" LIMIT="$LIMIT" RECOVERY_EMAIL="$RECOVERY_EMAIL" python3 - <<'PY'
import json, os
body = {
    "username": os.environ["USERNAME"],
    "password": os.environ["PASSWORD"],
    "quota": int(os.environ["QUOTA"]),
    "limit": int(os.environ["LIMIT"]),
}
if os.environ.get("RECOVERY_EMAIL"):
    body["recovery_email"] = os.environ["RECOVERY_EMAIL"]
print(json.dumps(body))
PY
)

echo "Creating mailbox ${USERNAME}@${DOMAIN} ..."
curl -sS -f -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  "$URI"
echo
