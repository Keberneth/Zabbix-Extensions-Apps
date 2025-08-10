#!/usr/bin/env bash
# -----------------------------------------------------------------------------
#  update-zbx_nbox.sh – Refresh NetBox + Zabbix stack (Fedora/SELinux friendly)
# -----------------------------------------------------------------------------
#  - Pulls the latest images declared in docker-compose-zbx_nbox.yml
#  - Recreates the stack (containers only) without data loss
#  - Cleans up dangling image layers
#  - Uses a fixed Compose project name to avoid name collisions
# -----------------------------------------------------------------------------
set -euo pipefail

COMPOSE_FILE="./docker-compose-zbx_nbox.yml"
PROJECT="${COMPOSE_PROJECT_NAME:-zbx_nbox}"
ENV_FILE="./.env"

info() { printf "▶ %s\n" "$*"; }
ok()   { printf "✓ %s\n" "$*"; }
err()  { printf "ERROR: %s\n" "$*\n" >&2; }

trap 'err "Command failed (line $LINENO): $BASH_COMMAND"' ERR

require() { command -v "$1" >/dev/null 2>&1 || { err "Missing: $1"; exit 1; }; }

require docker
docker compose version >/dev/null 2>&1 || { err "Need Docker Compose v2 (the 'docker compose' plugin)"; exit 1; }

[[ -f "$COMPOSE_FILE" ]] || { err "Compose file not found: $COMPOSE_FILE"; exit 1; }

# --- Generate .env with sane defaults (idempotent) --------------------------------
gen_if_blank () {
  local key="$1" def="$2"
  if ! grep -qE "^${key}=" "$ENV_FILE" 2>/dev/null; then
    echo "${key}=${def}" >> "$ENV_FILE"
  fi
}

if [[ ! -f "$ENV_FILE" ]]; then
  touch "$ENV_FILE"
fi

# Timezone + UID/GID for linuxserver.io image
gen_if_blank TZ "Europe/Stockholm"
gen_if_blank PUID "$(id -u)"
gen_if_blank PGID "$(id -g)"

# Zabbix DB creds
gen_if_blank ZBX_DB_NAME "zabbix"
gen_if_blank ZBX_DB_USER "zabbix"
if ! grep -q '^ZBX_DB_PASSWORD=' "$ENV_FILE" 2>/dev/null; then
  echo "ZBX_DB_PASSWORD=$(openssl rand -base64 24 | tr -d '\n' | tr '/+' 'Aa')" >> "$ENV_FILE"
fi

# NetBox DB creds
gen_if_blank NB_DB_NAME "netbox"
gen_if_blank NB_DB_USER "netbox"
if ! grep -q '^NB_DB_PASSWORD=' "$ENV_FILE" 2>/dev/null; then
  echo "NB_DB_PASSWORD=$(openssl rand -base64 24 | tr -d '\n' | tr '/+' 'Bb')" >> "$ENV_FILE"
fi

# NetBox SECRET_KEY (>=50 chars recommended)
if ! grep -q '^NB_SECRET_KEY=' "$ENV_FILE" 2>/dev/null; then
  if command -v python3 >/dev/null 2>&1; then
    echo -n "NB_SECRET_KEY=" >> "$ENV_FILE"
    python3 - <<'PY' >> "$ENV_FILE"
import secrets, string
alphabet = string.ascii_letters + string.digits + "-_.~"
print(''.join(secrets.choice(alphabet) for _ in range(64)))
PY
  else
    echo "NB_SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n' | tr '/+' 'Cc')" >> "$ENV_FILE"
  fi
fi

# Optional NetBox superuser bootstrap
gen_if_blank NB_SUPERUSER_NAME "admin"
gen_if_blank NB_SUPERUSER_EMAIL "admin@example.com"
if ! grep -q '^NB_SUPERUSER_PASSWORD=' "$ENV_FILE" 2>/dev/null; then
  echo "NB_SUPERUSER_PASSWORD=$(openssl rand -base64 24 | tr -d '\n' | tr '/+' 'Dd')" >> "$ENV_FILE"
fi

info "Pulling newer images (if any)…"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" pull

info "Stopping and removing old containers (keep volumes)…"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" down --remove-orphans

info "Starting all services with updated images (force recreate + pull always)…"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" up -d --force-recreate --pull=always

info "Pruning dangling image layers…"
docker image prune -f >/dev/null

ok "Update complete. Running containers:"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" ps