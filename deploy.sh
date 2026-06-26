#!/usr/bin/env bash
# Deploy MXroute Manager via Docker Compose (local directory or remote host over SSH).
# Optional saved targets: copy deploy.conf.example to deploy.conf and edit.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

CONF_FILE="${DEPLOY_CONF:-$ROOT/deploy.conf}"
DEFAULT_DIR="/opt/mxroute-manager"
BUILD_INFO="$ROOT/build_info.py"

DEPLOY_MODE=""
DEPLOY_DIR=""
REMOTE=""
SSH_PORT="22"

TAR_EXCLUDES=(
  --exclude='./.env'
  --exclude='./deploy.conf'
  --exclude='./.venv'
  --exclude='./.git'
  --exclude='./__pycache__'
  --exclude='./.pytest_cache'
  --exclude='./logs'
  --exclude='./site'
  --exclude='./mxroute-manager.db'
  --exclude='./mxroute-manager.db-journal'
  --exclude='./mxroute-manager.db-wal'
  --exclude='./mxtoolbox.db'
  --exclude='./mxtoolbox.db-journal'
  --exclude='./mxtoolbox.db-wal'
  --exclude='./build_info.py'
)

usage() {
  cat <<'EOF'
Usage: ./deploy.sh [options]

Interactive deploy to a local directory or a remote host (SSH + Docker Compose).
Does not overwrite an existing .env on the target; uploads local .env only when
the target has none.

Options:
  -h, --help          Show this help
  -y, --yes           Skip the menu (use saved deploy.conf or fail)
  -c, --config FILE   Config file (default: deploy.conf)

Config file format (shell assignments):
  DEPLOY_MODE=local|remote
  DEPLOY_DIR=/opt/mxroute-manager
  REMOTE=user@host        # remote mode only
  SSH_PORT=22             # optional
EOF
}

show_banner() {
  cat <<'EOF'
github.com/t0msh/mxroute-manager_          
 ____  _   _  ____ ___  _   _ _| |_ _____  
|    \( \ / )/ ___) _ \| | | (_   _) ___ | 
| | | |) X (| |  | |_| | |_| | | |_| ____| 
|_|_|_(_/ \_)_|   \___/|____/   \__)_____) 
 ____  _____ ____  _____  ____ _____  ____ 
|    \(____ |  _ \(____ |/ _  | ___ |/ ___)
| | | / ___ | | | / ___ ( (_| | ____| |    
|_|_|_\_____|_| |_\_____|\___ |_____)_|    
                        (_____|            

EOF
}

load_config() {
  # shellcheck disable=SC1090
  source "$CONF_FILE"
  DEPLOY_MODE="${DEPLOY_MODE:-}"
  DEPLOY_DIR="${DEPLOY_DIR:-$DEFAULT_DIR}"
  REMOTE="${REMOTE:-}"
  SSH_PORT="${SSH_PORT:-22}"
}

save_config() {
  cat >"$CONF_FILE" <<EOF
# Deploy target (gitignored). See deploy.conf.example.
DEPLOY_MODE=$DEPLOY_MODE
DEPLOY_DIR=$DEPLOY_DIR
REMOTE=$REMOTE
SSH_PORT=$SSH_PORT
EOF
  echo "Saved settings to $CONF_FILE"
}

prompt_deploy_settings() {
  show_banner
  echo "Deploy target"
  echo "─────────────"
  PS3="Choose: "
  select choice in "Local directory" "Remote server (SSH)" "Quit"; do
    case "$REPLY" in
      1)
        DEPLOY_MODE=local
        read -r -p "Deploy directory [$DEFAULT_DIR]: " input
        DEPLOY_DIR="${input:-$DEFAULT_DIR}"
        break
        ;;
      2)
        DEPLOY_MODE=remote
        read -r -p "SSH target (user@host): " REMOTE
        if [[ -z "$REMOTE" ]]; then
          echo "SSH target is required." >&2
          exit 1
        fi
        read -r -p "Remote directory [$DEFAULT_DIR]: " input
        DEPLOY_DIR="${input:-$DEFAULT_DIR}"
        read -r -p "SSH port [22]: " port_input
        SSH_PORT="${port_input:-22}"
        break
        ;;
      3)
        exit 0
        ;;
      *)
        echo "Invalid choice."
        ;;
    esac
  done

  read -r -p "Save these settings to deploy.conf? [y/N]: " save
  if [[ "${save,,}" == "y" ]]; then
    save_config
  fi
}

resolve_deploy_settings() {
  local assume_yes="${1:-false}"

  if [[ -f "$CONF_FILE" ]]; then
    load_config
    if [[ "$assume_yes" == "true" ]]; then
      return 0
    fi
    show_banner
    echo "Saved settings ($CONF_FILE):"
    echo "  mode:   $DEPLOY_MODE"
    echo "  dir:    $DEPLOY_DIR"
    [[ "$DEPLOY_MODE" == "remote" ]] && echo "  remote: $REMOTE (port $SSH_PORT)"
    PS3="Choose: "
    select choice in "Deploy with saved settings" "Reconfigure" "Quit"; do
      case "$REPLY" in
        1) return 0 ;;
        2) prompt_deploy_settings; return 0 ;;
        3) exit 0 ;;
      esac
    done
  fi

  if [[ "$assume_yes" == "true" ]]; then
    echo "No $CONF_FILE found. Run ./deploy.sh without -y to configure." >&2
    exit 1
  fi
  prompt_deploy_settings
}

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker is not installed or not on PATH." >&2
    exit 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    echo "docker compose is not available." >&2
    exit 1
  fi
}

require_remote_docker() {
  if ! remote "command -v docker >/dev/null 2>&1"; then
    echo "docker is not installed on $REMOTE." >&2
    exit 1
  fi
  if ! remote "docker compose version" >/dev/null 2>&1; then
    echo "docker compose is not available on $REMOTE." >&2
    exit 1
  fi
}

stamp_build_info() {
  if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    GIT_SHA="$(git -C "$ROOT" rev-parse --short HEAD)"
    GIT_BRANCH="$(git -C "$ROOT" branch --show-current)"
    GIT_DESCRIBE="$(git -C "$ROOT" describe --tags --always --dirty 2>/dev/null || git -C "$ROOT" rev-parse --short HEAD)"
  else
    GIT_SHA=""
    GIT_BRANCH=""
    GIT_DESCRIBE=""
  fi

  cat >"$BUILD_INFO" <<EOF
"""Auto-generated by deploy.sh — do not edit."""

BUILD_SHA = "${GIT_SHA}"
BUILD_BRANCH = "${GIT_BRANCH}"
BUILD_DESCRIBE = "${GIT_DESCRIBE}"
EOF

  if [[ -n "$GIT_SHA" ]]; then
    echo "Build stamp: ${GIT_BRANCH}@${GIT_SHA} (${GIT_DESCRIBE})"
  else
    cp -f "$ROOT/build_info.default.py" "$BUILD_INFO"
    echo "Build stamp: (no git metadata — using build_info.default.py)"
  fi
}

cleanup_build_info() {
  rm -f "$BUILD_INFO"
}

ensure_build_info_for_docker() {
  if [[ ! -f "$BUILD_INFO" ]]; then
    cp -f "$ROOT/build_info.default.py" "$BUILD_INFO"
  fi
}

sync_env_if_needed() {
  local target_dir="$1"
  local env_path="$target_dir/.env"

  if [[ -f "$env_path" ]]; then
    return 0
  fi
  if [[ -f "$ROOT/.env" ]]; then
    echo "Uploading local .env (target had none)..."
    mkdir -p "$target_dir"
    cp "$ROOT/.env" "$env_path"
    return 0
  fi
  echo "Warning: no .env on target or in project root."
  echo "  Copy .env.example to .env and configure before starting the app."
  echo "  See docs/getting-started.md"
}

stream_tar_to_dir() {
  local target_dir="$1"
  mkdir -p "$target_dir"
  tar -C "$ROOT" "${TAR_EXCLUDES[@]}" -czf - . | tar -C "$target_dir" -xzf -
}

compose_up() {
  local target_dir="$1"
  require_docker
  ensure_build_info_for_docker
  (
    cd "$target_dir"
    docker compose down 2>/dev/null || true
    docker compose up -d --build --force-recreate
  )
}

deploy_local() {
  echo "Deploying to local directory: $DEPLOY_DIR"
  stamp_build_info
  trap cleanup_build_info EXIT

  stream_tar_to_dir "$DEPLOY_DIR"
  cp -f "$BUILD_INFO" "$DEPLOY_DIR/build_info.py"
  sync_env_if_needed "$DEPLOY_DIR"
  compose_up "$DEPLOY_DIR"

  echo "Deployment complete. App listening on http://127.0.0.1:5000"
  echo "Put TLS in front for production — see docs/reverse-proxy.md"
}

deploy_remote() {
  local remote_host="${REMOTE#*@}"
  local ssh_control="/tmp/mxroute-deploy-${USER}-${remote_host}-${SSH_PORT}"
  local -a ssh_opts=(
    -p "$SSH_PORT"
    -o ConnectTimeout=10
    -o ControlMaster=auto
    -o "ControlPath=${ssh_control}"
    -o ControlPersist=300
  )

  remote() {
    ssh "${ssh_opts[@]}" "$REMOTE" "$@"
  }

  cleanup_ssh() {
    ssh "${ssh_opts[@]}" -O exit "$REMOTE" 2>/dev/null || true
  }
  trap cleanup_ssh EXIT

  echo "Connecting to $REMOTE..."
  remote "echo connected" >/dev/null
  require_remote_docker

  stamp_build_info
  trap 'cleanup_ssh; cleanup_build_info' EXIT

  echo "Packaging and streaming to $REMOTE:$DEPLOY_DIR..."
  remote "mkdir -p '$DEPLOY_DIR'"
  tar -C "$ROOT" "${TAR_EXCLUDES[@]}" -czf - . | ssh "${ssh_opts[@]}" "$REMOTE" "tar -C '$DEPLOY_DIR' -xzf -"
  scp -P "$SSH_PORT" -o ControlPath="$ssh_control" "$BUILD_INFO" "$REMOTE:$DEPLOY_DIR/build_info.py" >/dev/null

  if remote "test -f '$DEPLOY_DIR/.env'"; then
    :
  elif [[ -f "$ROOT/.env" ]]; then
    echo "Uploading local .env (remote had none)..."
    scp -P "$SSH_PORT" -o ControlPath="$ssh_control" "$ROOT/.env" "$REMOTE:$DEPLOY_DIR/.env" >/dev/null
  else
    echo "Warning: no .env on remote or in project root."
    echo "  Copy .env.example to .env on the server before first start."
    echo "  See docs/getting-started.md"
  fi

  echo "Building and starting container on remote host..."
  remote "cd '$DEPLOY_DIR' && docker compose down 2>/dev/null || true"
  remote "cd '$DEPLOY_DIR' && docker compose up -d --build --force-recreate"

  echo "Deployment complete. App listening on http://${remote_host}:5000"
  echo "Put TLS in front for production — see docs/reverse-proxy.md"
}

main() {
  local assume_yes=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h | --help)
        usage
        exit 0
        ;;
      -y | --yes)
        assume_yes=true
        shift
        ;;
      -c | --config)
        CONF_FILE="$2"
        shift 2
        ;;
      *)
        echo "Unknown option: $1" >&2
        usage >&2
        exit 1
        ;;
    esac
  done

  resolve_deploy_settings "$assume_yes"

  case "$DEPLOY_MODE" in
    local) deploy_local ;;
    remote)
      if [[ -z "$REMOTE" ]]; then
        echo "REMOTE is not set." >&2
        exit 1
      fi
      deploy_remote
      ;;
    *)
      echo "DEPLOY_MODE must be 'local' or 'remote'." >&2
      exit 1
      ;;
  esac
}

main "$@"
