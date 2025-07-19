#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  update‑zbx_nbox.sh  –  refresh NetBox + Zabbix containers on Fedora
# ---------------------------------------------------------------------------
#  * pulls the latest tags declared in docker-compose-zbx_nbox.yml
#  * recreates the stack with zero data loss
#  * prunes dangling images afterwards
# ---------------------------------------------------------------------------
set -euo pipefail

COMPOSE_FILE="./docker-compose-zbx_nbox.yml"
DC="docker compose -f $COMPOSE_FILE"

echo "▶ Pulling newer images (if any)…"
$DC pull

echo "▶ Stopping and removing old containers (keep volumes)…"
$DC down --remove-orphans

echo "▶ Starting Zabbix services with updated images (force recreate and pull always)…"
$DC up -d --force-recreate --pull always zabbix-server zabbix-web

echo "▶ Starting NetBox services with updated images (force recreate and pull always)…"
$DC up -d --force-recreate --pull always netbox nbox-postgres nbox-redis

echo "▶ Pruning dangling image layers…"
docker image prune -f

echo "✓ Update complete. Running containers:"
$DC ps
