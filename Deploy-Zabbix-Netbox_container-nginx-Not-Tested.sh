#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# deploy-zbx_nbox.sh – NetBox + Zabbix (Fedora/RHEL-friendly)
# Source: https://github.com/Keberneth/Zabbix-Extensions-Apps/tree/main/Docker%20Zabbix%20Netbox
# ---------------------------------------------------------------------------
set -euo pipefail

log(){ printf "▶ %s\n" "$*"; }
die(){ printf "❌ %s\n" "$*" >&2; exit 1; }

[[ ${EUID:-$(id -u)} -eq 0 ]] || die "Run as root."

# --- 0) OS pkgs --------------------------------------------------------------
source /etc/os-release
ID_LIKE=${ID_LIKE:-$ID}
case "$ID$ID_LIKE" in
  *rhel*|*fedora*|*rocky*) PKG=(dnf -q);    INSTALL=("${PKG[@]}" install -y); UPDATE=("${PKG[@]}" -y update -q);;
  *debian*|*ubuntu*)       PKG=(apt-get -qq); INSTALL=("${PKG[@]}" install -y); UPDATE=("${PKG[@]}" update -qq);;
  *suse*|*opensuse*)       PKG=(zypper);   INSTALL=("${PKG[@]}" -n install);  UPDATE=("${PKG[@]}" -n refresh);;
  *) die "Unsupported distro: $ID";;
esac

log "Installing Docker Engine, Compose plugin, nginx, git …"
"${UPDATE[@]}"
if [[ "$ID" =~ (fedora|rocky|rhel) ]]; then
  "${INSTALL[@]}" dnf-plugins-core || true
  (command -v dnf-3 >/dev/null && dnf-3 config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo) || \
  dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
  "${UPDATE[@]}"
  "${INSTALL[@]}" docker-ce docker-ce-cli containerd.io docker-compose-plugin nginx git python3 jq || true
elif [[ "$ID" =~ (debian|ubuntu) ]]; then
  "${INSTALL[@]}" docker.io docker-compose-plugin nginx git python3 jq
else
  "${INSTALL[@]}" docker docker-compose nginx git python3 jq || true
fi
systemctl enable --now docker
systemctl enable --now nginx

# Compose CLI detection
if docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
else
  die "Docker Compose not found."
fi

# --- 1) Inputs ---------------------------------------------------------------
read -rp "FQDN for NetBox  [netbox.example.com] : " FQDN_NB
FQDN_NB=${FQDN_NB:-netbox.example.com}
read -rp "FQDN for Zabbix [zabbix.example.com] : " FQDN_ZB
FQDN_ZB=${FQDN_ZB:-zabbix.example.com}

# --- 2) Get compose from repo ------------------------------------------------
WORKDIR=/tmp/zbx_nbox_install
REPO=https://github.com/Keberneth/Zabbix-Extensions-Apps.git
SUBDIR="Docker Zabbix Netbox"
mkdir -p "$WORKDIR"
cd "$WORKDIR"
rm -rf Zabbix-Extensions-Apps || true
log "Cloning $REPO …"
git clone --depth 1 "$REPO" >/dev/null
BASE="Zabbix-Extensions-Apps/$SUBDIR"
[[ -d "$BASE" ]] || die "Expected directory not found: $BASE"
COMPOSE_SRC=$(ls "$BASE"/*.yml "$BASE"/*.yaml 2>/dev/null | head -n1 || true)
[[ -n "${COMPOSE_SRC:-}" ]] || die "No docker-compose YAML found in $BASE"

DSTROOT=/docker
mkdir -p "$DSTROOT"
COMPOSE_FILE="$DSTROOT/$(basename "$COMPOSE_SRC")"
cp "$COMPOSE_SRC" "$COMPOSE_FILE"

# --- 3) Override: ports + SELinux labels off on services that trip runc -------
OVERRIDE_FILE="$DSTROOT/docker-compose.override.yml"
cat > "$OVERRIDE_FILE" <<'YML'
services:
  # repo maps host 8000 -> container 8080; bind to loopback only
  netbox:
    ports:
      - "127.0.0.1:8000:8080"
    security_opt:
      - label=disable

  # repo maps host 8080 -> container 8080; bind to loopback only
  zabbix-web:
    ports:
      - "127.0.0.1:8080:8080"
    security_opt:
      - label=disable

  # built-in agent (bridge network)
  zabbix-agent:
    security_opt:
      - label=disable

  # host agent (host network/privileged) – always disable labels here
  zabbix-agent-host:
    security_opt:
      - label=disable
YML

# --- 4) Disable SELinux labeling in dockerd globally --------------------------
log "Ensuring Docker daemon has selinux-enabled=false …"
mkdir -p /etc/docker
if [[ -f /etc/docker/daemon.json ]]; then
  # merge (jq if available, else python3)
  if command -v jq >/dev/null 2>&1; then
    tmp=$(mktemp)
    jq '. + {"selinux-enabled": false}' /etc/docker/daemon.json > "$tmp" || echo '{"selinux-enabled": false}' > "$tmp"
    mv "$tmp" /etc/docker/daemon.json
  else
    python3 - <<'PY'
import json,sys,os
p="/etc/docker/daemon.json"
data={}
if os.path.isfile(p):
  try:
    with open(p) as f: data=json.load(f)
  except Exception: data={}
data["selinux-enabled"]=False
with open(p,"w") as f: json.dump(data,f,indent=2)
PY
  fi
else
  echo '{"selinux-enabled": false}' > /etc/docker/daemon.json
fi
systemctl restart docker

# --- 5) TLS + nginx -----------------------------------------------------------
mkdir -p /etc/ssl/private /etc/ssl/certs
mkcert(){
  local fq="${1-}"; [[ -n "$fq" ]] || die "mkcert(): missing FQDN"
  local crt="/etc/ssl/certs/${fq}.crt" key="/etc/ssl/private/${fq}.key"
  if [[ ! -f "$crt" || ! -f "$key" ]]; then
    log "Creating self-signed cert for $fq (valid 3 years) …"
    openssl req -x509 -nodes -days 1095 -newkey rsa:2048 -subj "/CN=$fq" -keyout "$key" -out "$crt" >/dev/null 2>&1
    chmod 600 "$key"
  fi
}
mkcert "$FQDN_NB"; mkcert "$FQDN_ZB"

cat > /etc/nginx/conf.d/netbox.conf <<NGINX
server {
  listen 443 ssl;
  http2 on;
  server_name $FQDN_NB;

  ssl_certificate     /etc/ssl/certs/$FQDN_NB.crt;
  ssl_certificate_key /etc/ssl/private/$FQDN_NB.key;

  location / {
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_pass http://127.0.0.1:8000;
  }
}
NGINX

cat > /etc/nginx/conf.d/zabbix.conf <<NGINX
server {
  listen 443 ssl;
  http2 on;
  server_name $FQDN_ZB;

  ssl_certificate     /etc/ssl/certs/$FQDN_ZB.crt;
  ssl_certificate_key /etc/ssl/private/$FQDN_ZB.key;

  location / {
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_pass http://127.0.0.1:8080;
  }
}
NGINX

if command -v setsebool >/dev/null 2>&1; then setsebool -P httpd_can_network_connect 1 || true; fi
nginx -t >/dev/null && systemctl reload nginx

# --- 6) Bring stack down cleanly to avoid container-name conflicts ------------
"${DC[@]}" -f "$COMPOSE_FILE" -f "$OVERRIDE_FILE" down --remove-orphans || true

# --- 7) Up --------------------------------------------------------------------
log "Pulling images & starting containers …"
"${DC[@]}" -f "$COMPOSE_FILE" -f "$OVERRIDE_FILE" pull
"${DC[@]}" -f "$COMPOSE_FILE" -f "$OVERRIDE_FILE" up -d

# --- 8) Update helper ---------------------------------------------------------
cat > /docker/update-zbx_nbox.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
COMPOSE_FILE="/docker/docker-compose-zbx_nbox.yml"
OVERRIDE_FILE="/docker/docker-compose.override.yml"
if docker compose version >/dev/null 2>&1; then
  DC="docker compose -f $COMPOSE_FILE -f $OVERRIDE_FILE"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose -f $COMPOSE_FILE -f $OVERRIDE_FILE"
else
  echo "Docker Compose not found." >&2; exit 1
fi
echo "▶ Pulling newer images…";         eval "$DC pull"
echo "▶ Down (keep volumes)…";          eval "$DC down --remove-orphans"
echo "▶ Up Zabbix…";                    eval "$DC up -d --force-recreate --pull always zabbix-server zabbix-web"
echo "▶ Up NetBox…";                    eval "$DC up -d --force-recreate --pull always netbox nbox-postgres nbox-redis"
echo "▶ Prune unused layers…";          docker image prune -f
echo "✓ Running:";                      eval "$DC ps"
SH
chmod +x /docker/update-zbx_nbox.sh

# --- 9) Summary ---------------------------------------------------------------
log "✓ All done!"
echo "   NetBox : https://$FQDN_NB/"
echo "   Zabbix : https://$FQDN_ZB/"
echo "   Compose: $COMPOSE_FILE"
echo "   Override: $OVERRIDE_FILE"
echo "   Update : /docker/update-zbx_nbox.sh"
