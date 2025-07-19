#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# install-zbx_nbox.sh  –  all‑in‑one installer for NetBox + Zabbix on Linux
# ---------------------------------------------------------------------------
set -euo pipefail
IFS=$'\n\t'

############################ 1. PREREQUISITES ###############################
echo "▶ Detecting distribution …"
source /etc/os-release
ID_LIKE=${ID_LIKE:-$ID}

case "$ID$ID_LIKE" in
  *debian*|*ubuntu*)    PKG="apt-get -qq";   INSTALL="$PKG install -y"; UPDATE="$PKG update -qq" ;;
  *rhel*|*fedora*|*rocky*) PKG="dnf -q";       INSTALL="$PKG install -y"; UPDATE="$PKG -y update -q" ;;
  *suse*|*opensuse*)   PKG="zypper";        INSTALL="$PKG -n install";  UPDATE="$PKG -n refresh" ;;
  *) echo "Unsupported distro: $ID"; exit 1 ;;
esac

echo "▶ Installing Docker Engine, docker‑compose, git, and nginx …"
$UPDATE
# --- Docker ---------------------------------------------------------------
if [[ "$ID" =~ (debian|ubuntu) ]]; then
  $INSTALL docker.io docker-compose-plugin nginx git
elif [[ "$ID" =~ (fedora|rocky|rhel) ]]; then
  $INSTALL docker docker-compose nginx git
elif [[ "$ID" =~ (suse|opensuse) ]]; then
  $INSTALL docker docker-compose nginx git-core
fi

systemctl enable --now docker
systemctl enable --now nginx

########################### 2. CLONE REPO & FILES ###########################
echo "▶ Cloning Keberneth/Zabbix-Tools …"
mkdir -p /tmp/zbx_nbox_install
cd /tmp/zbx_nbox_install
if [[ -d Zabbix-Tools ]]; then rm -rf Zabbix-Tools; fi
git clone --depth 1 https://github.com/Keberneth/Zabbix-Tools.git

# copy compose + helper script
mkdir -p /docker
cp Zabbix-Tools/Docker/*.yml          /docker/
cp Zabbix-Tools/Docker/*.sh           /docker/
# copy nginx template
cp Zabbix-Tools/Nginx/*.conf          /etc/nginx/conf.d/

COMPOSE_FILE="/docker/docker-compose-zbx_nbox.yml"
NGINX_NETBOX="/etc/nginx/conf.d/netbox.conf"
NGINX_ZABBIX="/etc/nginx/conf.d/zabbix.conf"

########################### 3. USER INPUT ###################################
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

########################### 4. PREPARE FILES ################################
echo "▶ Generating NetBox SECRET_KEY …"
SECRET_KEY=$(docker run --rm netboxcommunity/netbox:latest \
              python /opt/netbox/netbox/generate_secret_key.py)

# 4a. replace placeholders in compose file
sed -i \
  -e "s/PASTE_YOUR_64_CHARACTER_SECRET_HERE/$SECRET_KEY/" \
  "$COMPOSE_FILE"

# 4b. replace FQDNs + certificate placeholders in nginx files
sed -i "s/netbox.example.com/$FQDN_NB/g"   "$NGINX_NETBOX"
sed -i "s/zabbix.example.com/$FQDN_ZB/g"   "$NGINX_ZABBIX"

# (optional) generate self‑signed certs if you have none:
for fq in "$FQDN_NB" "$FQDN_ZB"; do
  CRT="/etc/ssl/certs/${fq}.crt"
  KEY="/etc/ssl/private/${fq}.key"
  if [[ ! -f "$CRT" ]]; then
    echo "▶ Creating self‑signed cert for $fq (valid 3 years) …"
    openssl req -x509 -nodes -days 1095 -newkey rsa:2048 \
      -subj "/CN=$fq" -keyout "$KEY" -out "$CRT" &>/dev/null
  fi
done

nginx -t && systemctl reload nginx

########################### 5. CREATE DIRS ##################################
mkdir -p /docker/{netbox/{media,reports,scripts,postgres-data},\
zabbix/postgres-data}

chcon -Rvt svirt_sandbox_file_t /docker   2>/dev/null || true   # SELinux

########################### 6. START STACK ##################################
echo "▶ Pulling images & starting containers …"
docker compose -f "$COMPOSE_FILE" pull
docker compose -f "$COMPOSE_FILE" up -d

########################### 7. NETBOX DB INIT ###############################
echo "▶ Running NetBox migrations …"
docker compose -f "$COMPOSE_FILE" exec -T netbox \
  python3 /opt/netbox/netbox/manage.py migrate

echo "▶ Creating NetBox super‑user …"
docker compose -f "$COMPOSE_FILE" exec -T netbox \
  bash -c "echo \"from django.contrib.auth import get_user_model; \
  User=get_user_model(); \
  User.objects.filter(username='$NB_USER').exists() or \
  User.objects.create_superuser('$NB_USER','admin@$FQDN_NB','$NB_PASS')\" \
  | python3 /opt/netbox/netbox/manage.py shell"

########################### 8. FINISHED #####################################
echo "✓ All done!"
echo "   NetBox  : https://$FQDN_NB/"
echo "   Zabbix  : https://$FQDN_ZB/  (default login: Admin / zabbix)"
