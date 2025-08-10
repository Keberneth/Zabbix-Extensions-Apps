#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# deploy-zbx_nbox.sh – all-in-one installer for NetBox + Zabbix on Fedora/RHEL
# ---------------------------------------------------------------------------
set -euo pipefail

# ------------------------------- 0. Helpers ---------------------------------
log() { printf "▶ %s\n" "$*"; }
die() { printf "❌ %s\n" "$*" >&2; exit 1; }

need_root() { [[ ${EUID:-$(id -u)} -eq 0 ]] || die "Run as root (sudo)."; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || die "Missing required cmd: $1"; }

# ------------------------------- 1. Detect ----------------------------------
need_root
log "Detecting distribution …"
source /etc/os-release
ID_LIKE=${ID_LIKE:-$ID}

case "$ID$ID_LIKE" in
  *rhel*|*fedora*|*rocky*)
    PKG=(dnf -q)
    INSTALL=("${PKG[@]}" install -y)
    UPDATE=("${PKG[@]}" -y update -q)
    ;;
  *debian*|*ubuntu*)
    PKG=(apt-get -qq)
    INSTALL=("${PKG[@]}" install -y)
    UPDATE=("${PKG[@]}" update -qq)
    ;;
  *suse*|*opensuse*)
    PKG=(zypper)
    INSTALL=("${PKG[@]}" -n install)
    UPDATE=("${PKG[@]}" -n refresh)
    ;;
  *)
    die "Unsupported distro: $ID"
    ;;
esac

# --------------------------- 2. Install prereqs -----------------------------
log "Installing Docker Engine, Compose, nginx, git …"
"${UPDATE[@]}"

if [[ "$ID" =~ (fedora|rocky|rhel) ]]; then
  # Prefer Docker CE repo for up-to-date Engine + compose plugin
  if ! command -v docker >/dev/null 2>&1; then
    "${INSTALL[@]}" dnf-plugins-core || true
    # Some distros name the command dnf instead of dnf-3; handle both
    (command -v dnf-3 >/dev/null 2>&1 && dnf-3 config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo) || \
    dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
    "${UPDATE[@]}"
    "${INSTALL[@]}" docker-ce docker-ce-cli containerd.io docker-compose-plugin
  else
    "${INSTALL[@]}" docker-compose-plugin nginx git
  fi
  "${INSTALL[@]}" nginx git || true
elif [[ "$ID" =~ (debian|ubuntu) ]]; then
  "${INSTALL[@]}" docker.io docker-compose-plugin nginx git
elif [[ "$ID" =~ (suse|opensuse) ]]; then
  "${INSTALL[@]}" docker docker-compose nginx git-core
fi

systemctl enable --now docker
systemctl enable --now nginx

# Determine compose CLI (v2 plugin preferred)
if docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
else
  die "Docker Compose not found. Install docker-compose-plugin or docker-compose."
fi

# --------------------------- 3. Clone repo & paths --------------------------
log "Cloning Keberneth/Zabbix-Extensions-Apps …"
WORKDIR=/tmp/zbx_nbox_install
mkdir -p "$WORKDIR"
cd "$WORKDIR"
[[ -d Zabbix-Extensions-Apps ]] && rm -rf Zabbix-Extensions-Apps
git clone --depth 1 https://github.com/Keberneth/Zabbix-Extensions-Apps.git

# Figure out the actual base folder used in the repo (defensive)
BASE=""
for d in Zabbix-Tools Zabbix-Extensions-Apps; do
  [[ -d "$d" ]] && BASE="$d" && break
done
[[ -z "$BASE" ]] && BASE=$(find . -maxdepth 1 -type d -not -name '.' | head -n1)
[[ -z "$BASE" ]] && die "Could not determine repo base folder."

# Expect Docker and Nginx subfolders (as per your original script)
DOCKER_DIR="$BASE/Docker"
NGINX_DIR="$BASE/Nginx"
[[ -d "$DOCKER_DIR" ]] || die "Expected directory not found: $DOCKER_DIR"
[[ -d "$NGINX_DIR"  ]] || die "Expected directory not found: $NGINX_DIR"

# Pick a compose file. Prefer something with zbx or nbox in its name; else first .yml
COMPOSE_FILE=""
if compgen -G "$DOCKER_DIR/*zbx*nbox*.yml" >/dev/null; then
  COMPOSE_FILE=$(ls "$DOCKER_DIR"/*zbx*nbox*.yml | head -n1)
else
  COMPOSE_FILE=$(ls "$DOCKER_DIR"/*.yml | head -n1)
fi
[[ -n "$COMPOSE_FILE" ]] || die "No compose YAML found in $DOCKER_DIR"

# Copy files into place
mkdir -p /docker
cp "$DOCKER_DIR"/*.yml /docker/
cp "$DOCKER_DIR"/*.sh  /docker/ || true
cp "$NGINX_DIR"/*.conf /etc/nginx/conf.d/

# Use the copy we just made
COMPOSE_FILE="/docker/$(basename "$COMPOSE_FILE")"
NGINX_NETBOX="/etc/nginx/conf.d/netbox.conf"
NGINX_ZABBIX="/etc/nginx/conf.d/zabbix.conf"

# ------------------------------- 4. Inputs ----------------------------------
read -rp "FQDN for NetBox  [netbox.example.com] : " FQDN_NB
FQDN_NB=${FQDN_NB:-netbox.example.com}

read -rp "FQDN for Zabbix [zabbix.example.com] : " FQDN_ZB
FQDN_ZB=${FQDN_ZB:-zabbix.example.com}

read -rp "NetBox admin username [admin]        : " NB_USER
NB_USER=${NB_USER:-admin}

while :; do
  read -rsp "NetBox admin password (hidden)    : " NB_PASS && echo
  read -rsp "Confirm password                  : " NB_PASS2 && echo
  [[ "$NB_PASS" == "$NB_PASS2" && -n "$NB_PASS" ]] && break
  echo " ❌  Passwords do not match – try again."
done

# --------------------------- 5. Prepare secrets/files -----------------------
log "Generating NetBox SECRET_KEY …"
SECRET_KEY=$("${DC[@]}" -f "$COMPOSE_FILE" config >/dev/null 2>&1 \
  && docker run --rm netboxcommunity/netbox:latest \
       python /opt/netbox/netbox/generate_secret_key.py \
  || docker run --rm netboxcommunity/netbox:latest \
       python /opt/netbox/netbox/generate_secret_key.py)

# Replace placeholders in compose & nginx files if they exist there
if [[ -f "$COMPOSE_FILE" ]]; then
  sed -i -e "s/PASTE_YOUR_64_CHARACTER_SECRET_HERE/$SECRET_KEY/g" "$COMPOSE_FILE" || true
fi

[[ -f "$NGINX_NETBOX" ]] && sed -i "s/netbox.example.com/$FQDN_NB/g" "$NGINX_NETBOX" || true
[[ -f "$NGINX_ZABBIX" ]] && sed -i "s/zabbix.example.com/$FQDN_ZB/g" "$NGINX_ZABBIX" || true

# TLS certs (self-signed if missing)
for fq in "$FQDN_NB" "$FQDN_ZB"; do
  CRT="/etc/ssl/certs/${fq}.crt"
  KEY="/etc/ssl/private/${fq}.key"
  if [[ ! -f "$CRT" || ! -f "$KEY" ]]; then
    log "Creating self-signed cert for $fq (valid 3 years) …"
    mkdir -p /etc/ssl/private /etc/ssl/certs
    openssl req -x509 -nodes -days 1095 -newkey rsa:2048 \
      -subj "/CN=$fq" -keyout "$KEY" -out "$CRT" >/dev/null 2>&1
    chmod 600 "$KEY"
  fi
done

# Validate and reload nginx
nginx -t >/dev/null && systemctl reload nginx || die "nginx config test failed."

# ------------------------------ 6. Volumes/SELinux --------------------------
mkdir -p /docker/{netbox/{media,reports,scripts,postgres-data},zabbix/postgres-data}
# Allow Docker to access volumes with SELinux enforcing
chcon -Rvt svirt_sandbox_file_t /docker 2>/dev/null || true

# ---------------------------- 7. Start the stack ----------------------------
log "Pulling images & starting containers …"
"${DC[@]}" -f "$COMPOSE_FILE" pull
"${DC[@]}" -f "$COMPOSE_FILE" up -d

# --------------------------- 8. NetBox DB init ------------------------------
log "Running NetBox migrations …"
"${DC[@]}" -f "$COMPOSE_FILE" exec -T netbox \
  python3 /opt/netbox/netbox/manage.py migrate

log "Creating NetBox super-user …"
"${DC[@]}" -f "$COMPOSE_FILE" exec -T netbox bash -lc "
python3 /opt/netbox/netbox/manage.py shell <<'PY'
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='$NB_USER').exists():
    User.objects.create_superuser('$NB_USER','admin@$FQDN_NB','$NB_PASS')
PY
"

log "✓ All done!"
echo "   NetBox : https://$FQDN_NB/"
echo "   Zabbix : https://$FQDN_ZB/  (default login: Admin / zabbix)"
