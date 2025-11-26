#!/bin/bash

# Manual fallback for known ports
declare -A manual_port_map=(
  [22]="SSH"
  [3306]="MySQL"
  [5432]="PostgreSQL"
  [6379]="Redis"
  [27017]="MongoDB"
)

tmpfile=$(mktemp)

# -- 1. Collect listening ports: port|pid|process --
ss -tnlp | awk '
  NR>1 && $1 == "LISTEN" {
    split($4, addr, ":")
    port=addr[length(addr)]
    pid=""; proc=""
    if (match($NF, /pid=[0-9]+,/)) {
      split($NF, a, ",")
      for (i in a) {
        if (match(a[i], /pid=[0-9]+/)) pid=substr(a[i], 5)
        if (match(a[i], /name=.*/)) {
          sub(/name=/, "", a[i])
          proc=a[i]
        }
      }
    }
    print port "|" pid "|" proc
  }
' | sort -u > "$tmpfile"

# -- 2. Output JSON --
echo "["

first=true
while IFS="|" read -r port pid proc; do
  [[ -z "$port" ]] && continue
  [[ -z "$proc" ]] && proc="unknown"

  # Default empty
  service_name=""
  description=""

  # -- Try to map PID → systemd unit name via /proc --
  if [[ -n "$pid" && "$pid" =~ ^[0-9]+$ && -d "/proc/$pid" ]]; then
    unit_path=$(cat /proc/$pid/cgroup 2>/dev/null | grep "system.slice" | grep ".service" | awk -F'/' '{print $NF}' | head -n 1)
    service_name="$unit_path"
  fi

  # -- Detect web service by unit name --
  if [[ "$service_name" =~ nginx ]]; then
    description="NGINX Web Server"
  elif [[ "$service_name" =~ apache2|httpd ]]; then
    description="Apache HTTP Server"
  fi

  # -- If no description yet, try ps --
  if [[ -z "$description" && -n "$pid" ]]; then
    description=$(ps -p "$pid" -o comm= 2>/dev/null | awk 'NR==2')
  fi

  # -- Fallback to port map --
  [[ -z "$description" ]] && description="${manual_port_map[$port]}"
  [[ -z "$description" ]] && description="N/A"

  # -- Format JSON --
  $first || echo ","
  first=false
  echo "  {"
  echo "    \"Port\": $port,"
  echo "    \"PID\": ${pid:-null},"
  echo "    \"Process\": \"${proc}\","
  echo "    \"ServiceName\": \"${service_name}\","
  echo "    \"Description\": \"${description}\""
  echo -n "  }"
done < "$tmpfile"

echo
echo "]"

rm -f "$tmpfile"

