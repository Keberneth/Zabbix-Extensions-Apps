#!/usr/bin/env bash
# install_network_map.sh
# Installs Zabbix Network Map API / report engine on a RHEL/Fedora-style system.

set -euo pipefail

REPO_URL="https://github.com/Keberneth/Zabbix-Extensions-Apps.git"
APP_DIR="/opt/network_map"
PYTHON_BIN="python3.12"
SYSTEMD_UNIT="/etc/systemd/system/network_map.service"
NGINX_CONF="/etc/nginx/conf.d/network_map.conf"

#-----------------------------
# Helpers
#-----------------------------

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "This script must be run as root." >&2
    exit 1
  fi
}

detect_pm() {
  if command -v dnf >/dev/null 2>&1; then
    echo "dnf"
  elif command -v yum >/dev/null 2>&1; then
    echo "yum"
  elif command -v apt-get >/dev/null 2>&1; then
    echo "apt-get"
  else
    echo ""
  fi
}

ensure_python() {
  if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    return 0
  fi

  local PM
  PM=$(detect_pm)

  if [[ -z "${PM}" ]]; then
    echo "ERROR: Could not find package manager and ${PYTHON_BIN} is not installed." >&2
    exit 1
  fi

  echo "[*] Installing ${PYTHON_BIN} using ${PM}..."
  case "${PM}" in
    dnf|yum)
      "${PM}" -y install "${PYTHON_BIN}"
      ;;
    apt-get)
      # For Debian/Ubuntu you may need to adjust the version name here.
      "${PM}" update
      "${PM}" -y install python3 python3-pip
      PYTHON_BIN="python3"
      ;;
  esac

  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "ERROR: ${PYTHON_BIN} is still not available after installation." >&2
    exit 1
  fi
}

ensure_nginx_and_tools() {
  local PM
  PM=$(detect_pm)

  if [[ -z "${PM}" ]]; then
    echo "WARNING: No supported package manager found. Assuming nginx, git and SELinux tools are already installed."
    return 0
  fi

  echo "[*] Installing nginx, git, and SELinux tools (if available)..."
  case "${PM}" in
    dnf|yum)
      "${PM}" -y install nginx git policycoreutils-python-utils || true
      ;;
    apt-get)
      "${PM}" update
      "${PM}" -y install nginx git policycoreutils-python-utils || true
      ;;
  esac
}

ensure_pip() {
  echo "[*] Ensuring pip is available for ${PYTHON_BIN}..."
  if ! "${PYTHON_BIN}" -m pip --version >/dev/null 2>&1; then
    if "${PYTHON_BIN}" -m ensurepip --upgrade >/dev/null 2>&1; then
      echo "[*] Bootstrapped pip via ensurepip."
    else
      echo "ERROR: pip is not available for ${PYTHON_BIN} and ensurepip failed." >&2
      exit 1
    fi
  fi
}

install_python_packages() {
  echo "[*] Installing Python packages for Network Map..."
  "${PYTHON_BIN}" -m pip install --upgrade pip

  "${PYTHON_BIN}" -m pip install \
    fastapi \
    "uvicorn[standard]" \
    requests \
    openpyxl \
    networkx \
    numpy \
    scipy
}

create_directories() {
  echo "[*] Creating application directories..."
  mkdir -p "${APP_DIR}"
  mkdir -p "${APP_DIR}/static"
  mkdir -p "${APP_DIR}/reports"
  mkdir -p "${APP_DIR}/__pycache__"
}

deploy_app_files() {
  echo "[*] Cloning repository and deploying Network Map application..."
  local TMP_DIR
  TMP_DIR=$(mktemp -d /tmp/zabbix-extensions-apps.XXXXXX)

  git clone "${REPO_URL}" "${TMP_DIR}"

  if [[ ! -d "${TMP_DIR}/Network Map/network_map" ]]; then
    echo "ERROR: Expected directory \"Network Map/network_map\" not found in cloned repo." >&2
    rm -rf "${TMP_DIR}"
    exit 1
  fi

  # Copy all contents of network_map into /opt/network_map
  cp -r "${TMP_DIR}/Network Map/network_map/." "${APP_DIR}/"

  rm -rf "${TMP_DIR}"

  echo "[*] Application files deployed to ${APP_DIR}."
}

create_systemd_unit() {
  echo "[*] Creating systemd service at ${SYSTEMD_UNIT}..."

  cat > "${SYSTEMD_UNIT}" <<EOF
[Unit]
Description=Zabbix Network Map API
After=network.target

[Service]
User=root
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/env ${PYTHON_BIN} -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable network_map.service
}

create_nginx_conf() {
  echo "[*] Creating nginx reverse proxy configuration..."

  read -r -p "Enter FQDN for Network Map (e.g. map.example.com) [default: localhost]: " FQDN
  FQDN=${FQDN:-localhost}

  mkdir -p "$(dirname "${NGINX_CONF}")"

  cat > "${NGINX_CONF}" <<EOF
server {
    listen 80;
    server_name ${FQDN};

    # Static files
    location /static/ {
        alias ${APP_DIR}/static/;
    }

    # API / application
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Uncomment and adjust for HTTPS:
    # listen 443 ssl;
    # ssl_certificate     /etc/letsencrypt/live/${FQDN}/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/${FQDN}/privkey.pem;
}
EOF

  # Validate nginx config if nginx binary exists
  if command -v nginx >/dev/null 2>&1; then
    nginx -t
  fi
}

configure_selinux() {
  if command -v getenforce >/dev/null 2>&1 && [[ "$(getenforce)" != "Disabled" ]]; then
    echo "[*] Configuring SELinux for nginx and ${APP_DIR}..."

    # Allow nginx (httpd_t) to connect to the backend API
    setsebool -P httpd_can_network_connect 1 || true

    # Label application files as httpd_sys_content_t
    if command -v semanage >/dev/null 2>&1; then
      semanage fcontext -a -t httpd_sys_content_t "${APP_DIR}(/.*)? " || true
    fi
    restorecon -R "${APP_DIR}" || true
  else
    echo "[*] SELinux not enforcing or getenforce not found; skipping SELinux adjustments."
  fi
}

set_permissions() {
  echo "[*] Setting permissions on ${APP_DIR}..."
  if id nginx >/dev/null 2>&1; then
    chown nginx:nginx -R "${APP_DIR}"
  fi
  chmod 755 -R "${APP_DIR}"
}

start_services() {
  echo "[*] Starting services..."
  systemctl restart network_map.service

  if command -v nginx >/dev/null 2>&1; then
    systemctl restart nginx
  fi

  systemctl status network_map.service --no-pager || true
}

#-----------------------------
# Main
#-----------------------------
require_root
ensure_python
ensure_nginx_and_tools
ensure_pip
install_python_packages
create_directories
deploy_app_files
create_systemd_unit
create_nginx_conf
configure_selinux
set_permissions
start_services

echo
echo "Installation completed."
echo "Network Map API should now be available behind nginx on port 80."
echo "Application directory: ${APP_DIR}"
echo "Systemd unit: ${SYSTEMD_UNIT}"
echo "Nginx conf: ${NGINX_CONF}"
