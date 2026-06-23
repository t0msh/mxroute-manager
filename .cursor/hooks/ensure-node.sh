# shellcheck shell=bash
# Sourced by aislop wrappers. Requires Node >= 20.12 (aislop / @clack/core).
ensure_aislop_node() {
	local root="${1:-.}"
	local ver major minor

	if command -v node >/dev/null 2>&1; then
		ver="$(node -p 'process.versions.node')"
		major="${ver%%.*}"
		minor="${ver#*.}"
		minor="${minor%%.*}"
		if [ "$major" -gt 20 ] || { [ "$major" -eq 20 ] && [ "$minor" -ge 12 ]; }; then
			return 0
		fi
	fi

	export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
	if [ -s "$NVM_DIR/nvm.sh" ]; then
		# shellcheck disable=SC1091
		. "$NVM_DIR/nvm.sh"
		if [ -f "$root/.nvmrc" ]; then
			( cd "$root" && nvm install >/dev/null 2>&1 || true )
			( cd "$root" && nvm use >/dev/null 2>&1 || true )
		else
			nvm install 22 >/dev/null 2>&1 || true
			nvm use 22 >/dev/null 2>&1 || true
		fi
		if command -v node >/dev/null 2>&1; then
			ver="$(node -p 'process.versions.node')"
			major="${ver%%.*}"
			minor="${ver#*.}"
			minor="${minor%%.*}"
			if [ "$major" -gt 20 ] || { [ "$major" -eq 20 ] && [ "$minor" -ge 12 ]; }; then
				return 0
			fi
		fi
	fi

	echo "aislop requires Node.js 20.12+ (found $(node -v 2>/dev/null || echo 'none'))." >&2
	echo "Upgrade: nvm install 22 && nvm alias default 22" >&2
	echo "Or: https://nodejs.org/ (LTS 22+)" >&2
	return 1
}
