#!/usr/bin/env bash
set -euo pipefail

# -----------------------------
# Settings
# -----------------------------
GIT_URL="https://github.com/Keberneth/Zabbix-Extensions-Apps.git"
CLONE_DIR="/opt/zabbix-extensions-apps"
APP_SRC_SUBDIR="Network Map V2"
APP_TARGET_DIR="/opt/network_map"
NGINX_CONF_TARGET="/etc/nginx/conf.d/network_map.conf"
SERVICE_TARGET="/etc/systemd/system/network_map.service"
ENV_FILE="/etc/sysconfig/network_map"

PYTHON_BIN="python3.12"

# -----------------------------
# Root check
# -----------------------------
if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root." >&2
  exit 1
fi

# -----------------------------
# Detect package manager (RHEL)
# -----------------------------
if command -v dnf >/dev/null 2>&1; then
  PM="dnf"
elif command -v yum >/dev/null 2>&1; then
  PM="yum"
else
  echo "Neither dnf nor yum found. This script is for RHEL-based systems." >&2
  exit 1
fi

# -----------------------------
# Ask for FQDN and credentials
# -----------------------------
read -rp "Enter FQDN for Network Map (e.g. map.example.com): " FQDN
FQDN=${FQDN:-map.example.com}

# Try to use existing env as defaults if set
DEFAULT_ZABBIX_URL=${ZABBIX_URL:-"https://zabbix.example.se/api_jsonrpc.php"}
DEFAULT_ZABBIX_TOKEN=${ZABBIX_TOKEN:-"this_is_a_fake_token_for_example_purposes"}
DEFAULT_NETBOX_URL=${NETBOX_URL:-"https://netbox.example.se"}
DEFAULT_NETBOX_TOKEN=${NETBOX_TOKEN:-"this_is_a_fake_token_for_example_purposes"}

echo "Zabbix / NetBox configuration:"
read -rp "Zabbix URL [${DEFAULT_ZABBIX_URL}]: " ZABBIX_URL
ZABBIX_URL=${ZABBIX_URL:-$DEFAULT_ZABBIX_URL}

read -rp "Zabbix API token [${DEFAULT_ZABBIX_TOKEN}]: " ZABBIX_TOKEN
ZABBIX_TOKEN=${ZABBIX_TOKEN:-$DEFAULT_ZABBIX_TOKEN}

read -rp "NetBox URL [${DEFAULT_NETBOX_URL}]: " NETBOX_URL
NETBOX_URL=${NETBOX_URL:-$DEFAULT_NETBOX_URL}

read -rp "NetBox API token [${DEFAULT_NETBOX_TOKEN}]: " NETBOX_TOKEN
NETBOX_TOKEN=${NETBOX_TOKEN:-$DEFAULT_NETBOX_TOKEN}

echo
read -rp "Use environment file (/etc/sysconfig/network_map) and let config.py read Zabbix/NetBox from env (with fallback)? [y/N]: " USE_ENV
USE_ENV=${USE_ENV,,}  # to lower

# -----------------------------
# Install OS packages
# -----------------------------
echo "[*] Installing OS dependencies (Python 3.12, nginx, git, SELinux tools)..."
$PM -y install python3.12 python3.12-pip nginx git policycoreutils-python-utils || {
  echo "Failed to install packages with $PM" >&2
  exit 1
}

# -----------------------------
# Ensure python3.12 exists
# -----------------------------
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3.12 not found even after installation." >&2
  exit 1
fi

# -----------------------------
# Pip dependencies
# -----------------------------
echo "[*] Installing Python packages for Network Map..."
"$PYTHON_BIN" -m pip install --upgrade pip

"$PYTHON_BIN" -m pip install \
  fastapi \
  "uvicorn[standard]" \
  requests \
  openpyxl \
  networkx \
  numpy \
  scipy

# -----------------------------
# Clone / update Git repo
# -----------------------------
if [[ -d "$CLONE_DIR/.git" ]]; then
  echo "[*] Updating existing repo in $CLONE_DIR..."
  git -C "$CLONE_DIR" pull --ff-only
else
  echo "[*] Cloning repo to $CLONE_DIR..."
  rm -rf "$CLONE_DIR"
  git clone "$GIT_URL" "$CLONE_DIR"
fi

# -----------------------------
# Deploy application to /opt/network_map
# -----------------------------
SRC_ROOT="$CLONE_DIR/${APP_SRC_SUBDIR}"

if [[ ! -d "$SRC_ROOT/network_map" ]]; then
  echo "Could not find ${SRC_ROOT}/network_map in cloned repo." >&2
  exit 1
fi

echo "[*] Deploying application to $APP_TARGET_DIR..."
rm -rf "$APP_TARGET_DIR"
cp -r "$SRC_ROOT/network_map" "$APP_TARGET_DIR"

# Ensure proper ownership/permissions
chown -R nginx:nginx "$APP_TARGET_DIR"
chmod -R 755 "$APP_TARGET_DIR"

# -----------------------------
# Configure SELinux for /opt/network_map
# -----------------------------
echo "[*] Configuring SELinux for /opt/network_map..."
semanage fcontext -a -t httpd_sys_content_t "${APP_TARGET_DIR}(/.*)?" || true
restorecon -R "$APP_TARGET_DIR" || true
setsebool -P httpd_can_network_connect 1 || true

# -----------------------------
# Install nginx config
# -----------------------------
if [[ ! -f "$SRC_ROOT/nginx_network_map.conf" ]]; then
  echo "Could not find nginx_network_map.conf in ${SRC_ROOT}." >&2
  exit 1
fi

echo "[*] Installing nginx config..."
cp "$SRC_ROOT/nginx_network_map.conf" "$NGINX_CONF_TARGET"

# Replace server_name with chosen FQDN (for both HTTP and HTTPS blocks)
sed -i "s/server_name[[:space:]].*;/server_name ${FQDN};/g" "$NGINX_CONF_TARGET"

# -----------------------------
# Install systemd service
# -----------------------------
if [[ ! -f "$SRC_ROOT/network_map.service" ]]; then
  echo "Could not find network_map.service in ${SRC_ROOT}." >&2
  exit 1
fi

echo "[*] Installing systemd service..."
cp "$SRC_ROOT/network_map.service" "$SERVICE_TARGET"

# Ensure WorkingDirectory is correct
sed -i "s|WorkingDirectory=.*|WorkingDirectory=${APP_TARGET_DIR}|g" "$SERVICE_TARGET"

# Ensure ExecStart uses python3.12
sed -i "s|python3\\(.12\\)\\?|python3.12|g" "$SERVICE_TARGET"

# Optionally add EnvironmentFile for Zabbix/NetBox
if [[ "$USE_ENV" == "y" || "$USE_ENV" == "yes" ]]; then
  echo "[*] Creating environment file $ENV_FILE ..."
  cat > "$ENV_FILE" <<EOF
ZABBIX_URL="$ZABBIX_URL"
ZABBIX_TOKEN="$ZABBIX_TOKEN"
NETBOX_URL="$NETBOX_URL"
NETBOX_TOKEN="$NETBOX_TOKEN"
EOF
  chmod 600 "$ENV_FILE"

  if ! grep -q "^EnvironmentFile=" "$SERVICE_TARGET"; then
    sed -i '/^\[Service\]/a EnvironmentFile=-/etc/sysconfig/network_map' "$SERVICE_TARGET"
  fi
fi

# -----------------------------
# Patch config.py with Zabbix/NetBox settings
# -----------------------------
CONFIG_FILE="$APP_TARGET_DIR/config.py"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "ERROR: config.py not found in ${APP_TARGET_DIR}" >&2
  exit 1
fi

if ! grep -q "Added by install script: Zabbix/NetBox config" "$CONFIG_FILE"; then
  echo "[*] Patching config.py with Zabbix/NetBox settings..."
  if [[ "$USE_ENV" == "y" || "$USE_ENV" == "yes" ]]; then
    cat >> "$CONFIG_FILE" <<EOF

# --- Added by install script: Zabbix/NetBox config (env with fallback) ---
import os as _os_cfg_install

ZABBIX_URL = _os_cfg_install.getenv("ZABBIX_URL", "$ZABBIX_URL")
ZABBIX_TOKEN = _os_cfg_install.getenv("ZABBIX_TOKEN", "$ZABBIX_TOKEN")
NETBOX_URL = _os_cfg_install.getenv("NETBOX_URL", "$NETBOX_URL")
NETBOX_TOKEN = _os_cfg_install.getenv("NETBOX_TOKEN", "$NETBOX_TOKEN")
EOF
  else
    cat >> "$CONFIG_FILE" <<EOF

# --- Added by install script: Zabbix/NetBox config (static) ---
ZABBIX_URL = "$ZABBIX_URL"
ZABBIX_TOKEN = "$ZABBIX_TOKEN"
NETBOX_URL = "$NETBOX_URL"
NETBOX_TOKEN = "$NETBOX_TOKEN"
EOF
  fi
else
  echo "[*] config.py already patched earlier; skipping."
fi

# -----------------------------
# Enable and start services
# -----------------------------
echo "[*] Reloading systemd and enabling network_map.service..."
systemctl daemon-reload
systemctl enable network_map.service

echo "[*] Restarting nginx..."
nginx -t
systemctl restart nginx

echo "[*] Starting Network Map service..."
systemctl restart network_map.service

echo
echo "Installation complete."
echo "Check service status with:  systemctl status network_map.service"
echo "Open https://${FQDN}/ in your browser."
