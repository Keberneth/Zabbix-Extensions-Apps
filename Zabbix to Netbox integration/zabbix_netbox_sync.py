#!/usr/bin/env python3
"""
zabbix_netbox_sync.py

End-to-end integration:
- Pulls inventory and listening-service data from Zabbix
- Updates NetBox virtual machines:
    * OS + OS EOL (custom fields)
    * vCPUs and memory
    * Virtual disks (sizes in GB)
    * IP services (listening TCP ports)
"""

import os
import json
import math
import re
import warnings

import requests
import urllib3

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if hasattr(urllib3.exceptions, "SubjectAltNameWarning"):
    warnings.simplefilter("ignore", urllib3.exceptions.SubjectAltNameWarning)

# Hardcoded fallback values (used ONLY if env vars absent)
HARDCODED_ZABBIX_TOKEN = "REPLACE_ME"
HARDCODED_NETBOX_TOKEN = "REPLACE_ME"
HARDCODED_ZABBIX_URL   = "https://zabbix.DOMAIN.se/api_jsonrpc.php"
HARDCODED_NETBOX_URL   = "https://netbox.DOMAIN.se"

# Prefer environment variables but fallback to hardcoded values
ZABBIX_TOKEN = os.getenv("ZABBIX_TOKEN", HARDCODED_ZABBIX_TOKEN)
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN", HARDCODED_NETBOX_TOKEN)
ZABBIX_URL   = os.getenv("ZABBIX_URL", HARDCODED_ZABBIX_URL)
NETBOX_URL   = os.getenv("NETBOX_URL", HARDCODED_NETBOX_URL)

# SSL verification (set VERIFY_SSL=false in env if you must disable it)
VERIFY_SSL = os.getenv("VERIFY_SSL", "true").lower() == "true"

# Zabbix item names for listening services
LISTENING_ITEM_NAMES = [
    "Listening Services JSON",          # Windows
    "Linux Listening Services JSON",    # Linux
]

# NetBox endpoints
VM_ENDPOINT = f"{NETBOX_URL}/api/virtualization/virtual-machines/"
VDISK_ENDPOINT = f"{NETBOX_URL}/api/virtualization/virtual-disks/"
SERVICES_ENDPOINT = f"{NETBOX_URL}/api/ipam/services/"

# End-of-life base URL
EOL_API_BASE = "https://endoflife.date/api"

# ---------------------------------------------------------------------------
# Common helpers
# ---------------------------------------------------------------------------


def require_tokens():
    missing = []
    if not ZABBIX_TOKEN:
        missing.append("ZABBIX_TOKEN")
    if not NETBOX_TOKEN:
        missing.append("NETBOX_TOKEN")
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}"
        )


def convert_to_gb(bytes_str):
    """Convert a numeric string of bytes to whole gigabytes (ceiling)."""
    try:
        bytes_val = int(bytes_str)
        return math.ceil(bytes_val / (1024 ** 3))
    except (ValueError, TypeError):
        return "N/A"


def sanitize_filename(name):
    """Replace invalid filename characters with underscores (kept for completeness)."""
    return re.sub(r'[\\/*?:"<>|]', "_", name)


# ---------------------------------------------------------------------------
# Zabbix helpers
# ---------------------------------------------------------------------------


def zabbix_api_request(method, params):
    """Send a request to the Zabbix API and return 'result'."""
    headers = {"Content-Type": "application/json"}
    body = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "auth": ZABBIX_TOKEN,
        "id": 1,
    }
    resp = requests.post(ZABBIX_URL, headers=headers, json=body, verify=VERIFY_SSL)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Zabbix API error: {data['error']}")
    return data.get("result", [])


def get_all_host_groups():
    """Return a list of all host groups."""
    params = {
        "output": ["groupid", "name"],
        "selectHosts": ["hostid"],
        "sortfield": "name",
    }
    return zabbix_api_request("hostgroup.get", params)


def get_host_name(host_id):
    res = zabbix_api_request(
        "host.get", {"hostids": [host_id], "output": ["host"]}
    )
    return res[0]["host"] if res else f"hostid-{host_id}"


def get_item_value_by_name(host_id, item_name):
    """
    Return 'lastvalue' for the first item on 'host_id' whose name contains 'item_name'.
    If nothing is found, return 'N/A'.
    """
    params = {
        "hostids": [host_id],
        "search": {"name": item_name},
        "output": ["itemid", "name", "key_", "lastvalue"],
    }
    result = zabbix_api_request("item.get", params)
    if not result:
        return "N/A"
    return result[0].get("lastvalue", "N/A")


def get_item_value_by_key(host_id, item_key):
    """
    Return 'lastvalue' for the first item whose key_ matches 'item_key'.
    If nothing found, return 'N/A'.
    """
    params = {
        "hostids": [host_id],
        "search": {"key_": item_key},
        "output": ["key_", "lastvalue"],
    }
    result = zabbix_api_request("item.get", params)
    for item in result:
        if item["key_"] == item_key:
            return item.get("lastvalue", "N/A")
    return "N/A"


def get_linux_os_pretty_name(host_id):
    """Return the 'OSI PRETTY_NAME' value from Zabbix for the given host."""
    return get_item_value_by_name(host_id, "OSI PRETTY_NAME")


def get_disk_info_windows(host_id):
    """Retrieve disk information for a Windows host using vfs.fs.dependent.size."""
    disk_info = {}
    params = {
        "hostids": [host_id],
        "search": {"key_": "vfs.fs.dependent.size"},
        "output": ["key_", "lastvalue"],
    }
    result = zabbix_api_request("item.get", params)

    for item in result:
        key = item["key_"]
        value = item.get("lastvalue", "0")
        match = re.search(r"\[(.*?),total\]", key)
        if match:
            disk_label = match.group(1)
            disk_size_gb = convert_to_gb(value)
            disk_info[disk_label] = disk_size_gb
    return disk_info


def get_disk_info_linux(host_id):
    """
    Retrieve disk info for a Linux host by searching keys like:
      vfs.file.contents[/sys/block/sda/size]
    """
    disk_info = {}
    params = {
        "hostids": [host_id],
        "search": {"key_": "vfs.file.contents[/sys/block/"},
        "output": ["key_", "lastvalue"],
    }
    result = zabbix_api_request("item.get", params)

    if not result:
        print(f"[WARN] No disk data found for host ID: {host_id}")
        return disk_info

    for item in result:
        key = item["key_"]
        value = item.get("lastvalue", "N/A")
        match = re.search(r"vfs\\.file\\.contents\\[/sys/block/(.*?)/size\\]", key)
        if match:
            disk_label = match.group(1)
            disk_size_gb = convert_to_gb(value)
            disk_info[disk_label] = disk_size_gb
    return disk_info


def get_listening_services_from_zabbix(host_id):
    """
    Fetch listening-services JSON from Zabbix for a host.

    Returns:
        list of dict entries, or [] on error / not found.
    """
    for item_name in LISTENING_ITEM_NAMES:
        params = {
            "output": ["itemid", "name", "lastvalue"],
            "hostids": [host_id],
            "filter": {"name": item_name},
            "sortfield": "name",
        }
        items = zabbix_api_request("item.get", params)
        if not items:
            continue

        item = items[0]
        try:
            return json.loads(item.get("lastvalue", "[]"))
        except json.JSONDecodeError:
            print(
                f"[WARN] host_id={host_id}: item '{item_name}' lastvalue is not valid JSON"
            )
            return []
    # Nothing found
    return []


# ---------------------------------------------------------------------------
# NetBox helpers
# ---------------------------------------------------------------------------

HEADERS = {
    "Authorization": f"Token {NETBOX_TOKEN}" if NETBOX_TOKEN else "",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def nb_get(url, params=None):
    resp = requests.get(url, headers=HEADERS, params=params, verify=VERIFY_SSL)
    resp.raise_for_status()
    return resp.json()


def nb_post(url, payload):
    resp = requests.post(url, headers=HEADERS, json=payload, verify=VERIFY_SSL)
    resp.raise_for_status()
    return resp.json()


def nb_patch(url, payload):
    resp = requests.patch(url, headers=HEADERS, json=payload, verify=VERIFY_SSL)
    resp.raise_for_status()
    return resp.json()


def nb_delete(url):
    resp = requests.delete(url, headers=HEADERS, verify=VERIFY_SSL)
    # NetBox returns 204 on successful delete
    if resp.status_code not in (204, 404):
        print(f"[WARN] DELETE {url} → HTTP {resp.status_code}: {resp.text}")


def find_vm_by_substring(substring):
    """Searches for a VM in NetBox using the substring."""
    params = {"name__ic": substring, "limit": 0}
    data = nb_get(VM_ENDPOINT, params=params)
    results = data.get("results", [])
    if len(results) == 1:
        return results[0]
    elif len(results) > 1:
        print(f"[WARN] Multiple VMs found matching '{substring}'. Skipping.")
        return None
    else:
        print(f"[WARN] No VM found matching '{substring}'.")
        return None


def get_primary_ip_id(vm_id):
    data = nb_get(f"{VM_ENDPOINT}{vm_id}/")
    ip4 = data.get("primary_ip4")
    return ip4["id"] if ip4 else None


def list_existing_services(vm_id):
    """
    Return a dict {port:int -> service_object} for the VM.
    """
    params = {"virtual_machine_id": vm_id, "limit": 0}
    data = nb_get(SERVICES_ENDPOINT, params=params)
    existing = {}
    for svc in data.get("results", []):
        for port in svc.get("ports", []):
            existing[int(port)] = svc
    return existing


def _norm_str(val, field, port):
    """Return trimmed string if val is str else empty string; warn on unexpected types."""
    if isinstance(val, str):
        return val.strip()
    if val not in (None, "", 0, False, True):
        print(f"[WARN] Port {port}: ignoring non-string {field}={val!r}")
    return ""


def create_service(vm_id, ip_id, port, name, description):
    payload = {
        "name": name,
        "protocol": "tcp",
        "ports": [port],
        "virtual_machine": vm_id,
        "description": description,
    }
    if ip_id:
        payload["ipaddresses"] = [ip_id]
    nb_post(SERVICES_ENDPOINT, payload)
    print(f"[CREATED] Service {name} TCP/{port}")


def update_service(svc_id, name, description):
    payload = {"name": name, "description": description}
    nb_patch(f"{SERVICES_ENDPOINT}{svc_id}/", payload)
    print(f"[UPDATED] Service id={svc_id}: {name}")


def delete_service(svc_id, port, name):
    nb_delete(f"{SERVICES_ENDPOINT}{svc_id}/")
    print(f"[REMOVED] Service id={svc_id} TCP/{port}: {name}")


def update_services_for_vm(vm, services_entries):
    """
    Synchronise NetBox services for a VM based on Zabbix listening-services data.
    """
    vm_id = vm["id"]
    hostname = vm["name"]
    ip_id = get_primary_ip_id(vm_id)
    existing = list_existing_services(vm_id)  # {port:int -> service}

    if not services_entries:
        print(f"[INFO] {hostname}: no listening services entries; existing services may be pruned.")
    reported_ports = set()

    for e in services_entries:
        try:
            port = int(e.get("Port") or 0)
        except Exception:
            print(f"[WARN] Bad port value {e.get('Port')!r}, skipping entry")
            continue
        if not port:
            continue

        svcname = _norm_str(e.get("ServiceName"), "ServiceName", port)
        process = _norm_str(e.get("Process"), "Process", port)
        desc = _norm_str(e.get("Description"), "Description", port)

        if svcname:
            name = svcname
        elif process:
            name = process
            desc = desc or f"{process} listening on port {port}"
        else:
            print(f"[SKIP] Port {port}: no usable name (svc/process missing)")
            continue

        if not desc:
            desc = name

        reported_ports.add(port)

        if port in existing:
            svc = existing[port]
            if svc["name"] != name or (svc.get("description") or "") != desc:
                update_service(svc["id"], name, desc)
            else:
                print(f"[OK] {hostname}: TCP/{port} already correct")
        else:
            create_service(vm_id, ip_id, port, name, desc)

    # prune stale services
    for stale_port in set(existing) - reported_ports:
        svc = existing[stale_port]
        delete_service(svc["id"], stale_port, svc["name"])


def get_disks_for_vm(vm_id):
    """Return {disk_name: disk_object} for the VM."""
    params = {"virtual_machine_id": vm_id, "limit": 0}
    data = nb_get(VDISK_ENDPOINT, params=params)
    return {disk["name"]: disk for disk in data.get("results", [])}


def bulk_create_disks(disks_to_create):
    if not disks_to_create:
        return
    print(f"[INFO] Creating {len(disks_to_create)} new disk(s) in NetBox...")
    nb_post(VDISK_ENDPOINT, disks_to_create)


def bulk_update_disks(disks_to_update):
    if not disks_to_update:
        return
    print(f"[INFO] Updating {len(disks_to_update)} disk(s) in NetBox...")
    nb_patch(VDISK_ENDPOINT, disks_to_update)

def update_disks_for_vm(vm, disk_map):
    """
    Sync virtual disks in NetBox with Zabbix discovery for a VM.

    disk_map: {disk_name: size_gb} from Zabbix
    """
    vm_id = vm["id"]
    vm_name = vm["name"]

    # Existing disks in NetBox: {disk_name: disk_object}
    existing_disks = get_disks_for_vm(vm_id)

    disks_to_create = []
    disks_to_update = []
    disks_to_delete = []

    # Create/update based on Zabbix
    for disk_name, size in disk_map.items():
        if disk_name in existing_disks:
            disk = existing_disks[disk_name]
            disk_id = disk["id"]
            current_size = disk["size"]
            if current_size != size:
                disks_to_update.append({"id": disk_id, "size": size})
            else:
                print(f"[OK] Disk '{disk_name}' on VM '{vm_name}' is already correct.")
        else:
            disks_to_create.append(
                {
                    "virtual_machine": vm_id,
                    "name": disk_name,
                    "size": size,
                }
            )

    # Any disk present in NetBox but not in Zabbix should be removed
    for disk_name, disk in existing_disks.items():
        if disk_name not in disk_map:
            disks_to_delete.append(disk)

    # Apply changes
    bulk_create_disks(disks_to_create)
    bulk_update_disks(disks_to_update)

    for disk in disks_to_delete:
        disk_id = disk["id"]
        disk_name = disk["name"]
        nb_delete(f"{VDISK_ENDPOINT}{disk_id}/")
        print(f"[REMOVED] Disk '{disk_name}' (id={disk_id}) from VM '{vm_name}' – no longer in Zabbix.")

def update_or_create_vm_resources(vm_record, new_memory, new_vcpus):
    """
    Updates the VM's memory and vcpus if needed (PATCH).
    """
    vm_id = vm_record.get("id")
    current_memory = vm_record.get("memory")
    current_vcpus = vm_record.get("vcpus")

    payload = {
        "memory": new_memory,
        "vcpus": new_vcpus,
        "status": "active",
    }

    if vm_record.get("site"):
        payload["site"] = vm_record["site"]["id"]
    if vm_record.get("cluster"):
        payload["cluster"] = vm_record["cluster"]["id"]
    if vm_record.get("tenant"):
        payload["tenant"] = vm_record["tenant"]["id"]

    if (current_memory is None or current_memory == 0) or (
        current_vcpus is None or current_vcpus == 0
    ):
        print(f"[INFO] Updating VM ID {vm_id} with missing resource fields.")
    elif current_memory == new_memory and current_vcpus == new_vcpus:
        print(
            f"[OK] VM ID {vm_id}: resources already correct "
            f"(memory={current_memory}, vcpus={current_vcpus})."
        )
        return

    nb_patch(f"{VM_ENDPOINT}{vm_id}/", payload)
    print(
        f"[UPDATED] VM ID {vm_id}: memory={new_memory} MB, vcpus={new_vcpus}"
    )


# ---------------------------------------------------------------------------
# OS + EOL helpers
# ---------------------------------------------------------------------------


def parse_os_vendor_and_version(os_string: str):
    """
    Parse the OS string to extract the vendor and appropriate version
    for endoflife.date.
    """
    if not os_string:
        return None, None

    os_lower = os_string.lower()

    # Ubuntu
    if "ubuntu" in os_lower:
        match = re.search(r"ubuntu\s+(\d+\.\d+)", os_lower)
        if match:
            full_version = match.group(1)
            return "ubuntu", full_version
        return "ubuntu", None

    # Oracle Linux
    if "oracle linux" in os_lower:
        match = re.search(r"oracle linux.* (\d+)\.?", os_lower)
        if match:
            major_version = match.group(1)
            return "oracle-linux", major_version
        return "oracle-linux", None

    # Red Hat Enterprise Linux
    if "red hat enterprise linux" in os_lower:
        match = re.search(r"red hat enterprise linux.* (\d+)\.?", os_lower)
        if match:
            major_version = match.group(1)
            return "redhat", major_version
        return "redhat", None

    # Windows Server
    if "windows server" in os_lower:
        match = re.search(r"windows server.*?\b(\d{4})\b", os_lower)
        if match:
            return "windows-server", match.group(1)
        return "windows-server", None

    # Rocky Linux
    if "rocky linux" in os_lower:
        match = re.search(r"rocky linux (\d+)\.?", os_lower)
        if match:
            major_version = match.group(1)
            return "rocky-linux", major_version
        return "rocky-linux", None

    # SUSE Linux Enterprise Server
    if "suse linux enterprise server" in os_lower:
        match = re.search(r"suse linux enterprise server (\d+)(?:\s*sp(\d+))?", os_lower)
        if match:
            major_version = match.group(1)
            sp_version = match.group(2)
            if sp_version:
                cycle = f"{major_version}.{sp_version}"
            else:
                cycle = f"{major_version}"
            return "sles", cycle
        return "sles", None

    return None, None


def get_os_eol(os_name: str, os_version: str) -> str:
    """
    Fetch the End of Life (EOL) date for the given OS from endoflife.date API.
    Special handling for SLES which returns a list.
    """
    if not os_name or not os_version:
        return "Unknown"

    try:
        if os_name == "sles":
            url = f"{EOL_API_BASE}/sles.json"
            resp = requests.get(url, headers={"Accept": "application/json"}, verify=VERIFY_SSL)
            resp.raise_for_status()
            data = resp.json()
            for entry in data:
                if entry.get("cycle") == os_version:
                    eol = entry.get("eol")
                    return "Still Supported" if not eol else eol
            print(f"[WARN] SLES version {os_version} not found in EOL data.")
            return "Unknown"

        else:
            url = f"{EOL_API_BASE}/{os_name}/{os_version}.json"
            resp = requests.get(url, headers={"Accept": "application/json"}, verify=VERIFY_SSL)
            resp.raise_for_status()
            data = resp.json()
            return data.get("eol", "Unknown")

    except Exception as exc:
        print(f"[WARN] Error fetching EOL info for {os_name} {os_version}: {exc}")
        return "Unknown"


def update_vm_os(vm_record, new_os, os_eol):
    vm_id = vm_record.get("id")
    cf = vm_record.get("custom_fields", {}) or {}

    # If the fields are not present at all, assume they are not defined in NetBox
    if "operating_system" not in cf or "operating_system_EOL" not in cf:
        print(f"[WARN] VM ID {vm_id}: OS/EOL custom fields missing; skipping OS update.")
        return

    current_os = cf.get("operating_system")
    current_eol = cf.get("operating_system_EOL")

    if current_os == new_os and current_eol == os_eol:
        print(
            f"[OK] VM ID {vm_id}: OS/EOL already correct "
            f"(OS='{current_os}', EOL='{current_eol}')."
        )
        return

    payload = {
        "custom_fields": {
            "operating_system": new_os,
            "operating_system_EOL": os_eol,
        }
    }

    nb_patch(f"{VM_ENDPOINT}{vm_id}/", payload)
    print(
        f"[UPDATED] VM ID {vm_id}: operating_system='{new_os}', "
        f"operating_system_EOL='{os_eol}'"
    )

# ---------------------------------------------------------------------------
# Host inventory from Zabbix
# ---------------------------------------------------------------------------


def collect_host_inventory():
    """
    Generator yielding per-host inventory dictionaries:

    {
        "host_id": str,
        "host": str,
        "operating_system": str,
        "total_memory_gb": int or "N/A",
        "cores": str or number,
        "disks": {disk_name: size_gb},
    }
    """
    host_groups = get_all_host_groups()
    processed_host_ids = set()

    os_key = "system.sw.os"
    memory_key = "vm.memory.size[total]"

    for group in host_groups:
        group_name = group["name"]
        for host in group.get("hosts", []):
            host_id = host["hostid"]
            if host_id in processed_host_ids:
                continue
            processed_host_ids.add(host_id)

            host_name = get_host_name(host_id)

            # OS detection
            os_version = get_item_value_by_key(host_id, os_key)
            if "linux" in group_name.lower() or "linux" in str(os_version).lower():
                os_version = get_linux_os_pretty_name(host_id)

            # Memory
            memory_bytes = get_item_value_by_key(host_id, memory_key)
            memory_gb = convert_to_gb(memory_bytes)

            # Decide OS family for cores / disks
            group_lower = group_name.lower()
            os_lower = str(os_version).lower()
            if "windows" in group_lower or "windows" in os_lower:
                cores_key = 'wmi.get[root/cimv2,"Select NumberOfLogicalProcessors from Win32_ComputerSystem"]'
                disks = get_disk_info_windows(host_id)
            elif "linux" in group_lower or "linux" in os_lower:
                cores_key = "system.cpu.num"
                disks = get_disk_info_linux(host_id)
            else:
                cores_key = None
                disks = {}

            if cores_key:
                cores = get_item_value_by_key(host_id, cores_key)
            else:
                cores = "Unknown"

            yield {
                "host_id": host_id,
                "host": host_name,
                "operating_system": os_version,
                "total_memory_gb": memory_gb,
                "cores": cores,
                "disks": disks,
            }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def process_host(host_inv):
    host_name = host_inv["host"]
    host_id = host_inv["host_id"]
    print(f"\n=== Processing host {host_name} (ID {host_id}) ===")

    vm = find_vm_by_substring(host_name)
    if not vm:
        return

    # 1) OS + EOL
    os_value = host_inv.get("operating_system")
    os_vendor, os_version = parse_os_vendor_and_version(os_value or "")
    os_eol = get_os_eol(os_vendor, os_version) if os_vendor else "Unknown"
    update_vm_os(vm, os_value, os_eol)

    # 2) Resources (memory / vcpus)
    total_memory_gb = host_inv.get("total_memory_gb")
    cores = host_inv.get("cores")

    try:
        new_memory_mb = int(float(total_memory_gb) * 1000)
    except (TypeError, ValueError):
        new_memory_mb = None

    try:
        new_vcpus = round(float(cores), 2)
        if new_vcpus < 0.01:
            new_vcpus = None
    except (TypeError, ValueError):
        new_vcpus = None

    if new_memory_mb and new_vcpus:
        update_or_create_vm_resources(vm, new_memory_mb, new_vcpus)
    else:
        print(
            f"[WARN] Skipping resource update for {host_name}: "
            f"memory={total_memory_gb}, cores={cores}"
        )

    # 3) Disks
    disks = host_inv.get("disks") or {}
    if disks:
        update_disks_for_vm(vm, disks)
    else:
        print(f"[INFO] {host_name}: no disk data to sync.")

    # 4) Listening services
    services_entries = get_listening_services_from_zabbix(host_id)
    if services_entries:
        update_services_for_vm(vm, services_entries)
    else:
        print(f"[INFO] {host_name}: no listening-services JSON found in Zabbix.")


def main():
    require_tokens()
    for host_inv in collect_host_inventory():
        try:
            process_host(host_inv)
        except Exception as exc:
            print(f"[ERROR] Failed processing {host_inv.get('host')}: {exc}")


if __name__ == "__main__":
    main()
