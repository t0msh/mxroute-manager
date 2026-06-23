#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/.cursor/hooks/ensure-node.sh"
ensure_aislop_node "$ROOT"

cd "$ROOT"
exec npx --yes --package=aislop@latest aislop-mcp
