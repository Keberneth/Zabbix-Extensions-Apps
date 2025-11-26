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
import sys
import subprocess
import logging

import requests
import urllib3

# Logging
LOG_FILE = "/var/log/zabbix_netbox_sync.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)

# Configuration

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# urllib3 v2 removed SubjectAltNameWarning; guard safely
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



# Zabbix status reporting (for trigger)


# Configure these to match your Zabbix setup
ZABBIX_SENDER = os.getenv("ZABBIX_SENDER", "/usr/bin/zabbix_sender")
ZABBIX_SERVER = os.getenv("ZABBIX_SERVER", "127.0.0.1")          # Zabbix server address
ZABBIX_HOST   = os.getenv("ZABBIX_HOST", "netbox-sync-host")     # Host name in Zabbix
ZABBIX_KEY    = os.getenv("ZABBIX_KEY", "netbox.sync.status")    # Trapper item key


def report_status_to_zabbix(success: bool):
    """
    Send 1 (success) or 0 (failure) to a Zabbix trapper item via zabbix_sender.
    Does not raise if zabbix_sender fails – only logs a warning.
    """
    value = "1" if success else "0"
    cmd = [
        ZABBIX_SENDER,
        "-z", ZABBIX_SERVER,
        "-s", ZABBIX_HOST,
        "-k", ZABBIX_KEY,
        "-o", value,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logging.warning(
                "zabbix_sender failed (rc=%s): %s %s",
                result.returncode,
                result.stdout.strip(),
                result.stderr.strip(),
            )
        else:
            logging.info("Reported status=%s to Zabbix via zabbix_sender", value)
    except FileNotFoundError:
        logging.warning(
            "zabbix_sender not found at %s; cannot report status to Zabbix",
            ZABBIX_SENDER,
        )
    except Exception as exc:
        logging.warning("Failed to report status to Zabbix: %s", exc)



# Common helpers


def require_tokens():
    missing = []
    if not ZABBIX_TOKEN:
        missing.append("ZABBIX_TOKEN (env or hardcoded)")
    if not NETBOX_TOKEN:
        missing.append("NETBOX_TOKEN (env or hardcoded)")
    if missing:
        raise RuntimeError(
            f"Missing required credentials: {', '.join(missing)}"
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



# Zabbix helpers


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
        logging.warning("No disk data found for host ID: %s", host_id)
        return disk_info

    for item in result:
        key = item["key_"]
        value = item.get("lastvalue", "N/A")
        match = re.search(r"vfs\.file\.contents\[/sys/block/(.*?)/size\]", key)
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
            logging.warning(
                "host_id=%s: item '%s' lastvalue is not valid JSON",
                host_id,
                item_name,
            )
            return []
    # Nothing found
    return []



# NetBox helpers


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
        logging.warning("DELETE %s → HTTP %s: %s", url, resp.status_code, resp.text)


def find_vm_by_substring(substring):
    """Searches for a VM in NetBox using the substring."""
    params = {"name__ic": substring, "limit": 0}
    data = nb_get(VM_ENDPOINT, params=params)
    results = data.get("results", [])
    if len(results) == 1:
        return results[0]
    elif len(results) > 1:
        logging.warning("Multiple VMs found matching '%s'. Skipping.", substring)
        return None
    else:
        logging.warning("No VM found matching '%s'.", substring)
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
        logging.warning("Port %s: ignoring non-string %s=%r", port, field, val)
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
    logging.info("CREATED service %s TCP/%s", name, port)


def update_service(svc_id, name, description):
    payload = {"name": name, "description": description}
    nb_patch(f"{SERVICES_ENDPOINT}{svc_id}/", payload)
    logging.info("UPDATED service id=%s: %s", svc_id, name)


def delete_service(svc_id, port, name):
    nb_delete(f"{SERVICES_ENDPOINT}{svc_id}/")
    logging.info("REMOVED service id=%s TCP/%s: %s", svc_id, port, name)


def update_services_for_vm(vm, services_entries):
    """
    Synchronise NetBox services for a VM based on Zabbix listening-services data.
    """
    vm_id = vm["id"]
    hostname = vm["name"]
    ip_id = get_primary_ip_id(vm_id)
    existing = list_existing_services(vm_id)  # {port:int -> service}

    if not services_entries:
        logging.info(
            "%s: no listening services entries; existing services may be pruned.",
            hostname,
        )
    reported_ports = set()

    for e in services_entries:
        try:
            port = int(e.get("Port") or 0)
        except Exception:
            logging.warning("Bad port value %r, skipping entry", e.get("Port"))
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
            logging.info("SKIP port %s: no usable name (svc/process missing)", port)
            continue

        if not desc:
            desc = name

        reported_ports.add(port)

        if port in existing:
            svc = existing[port]
            if svc["name"] != name or (svc.get("description") or "") != desc:
                update_service(svc["id"], name, desc)
            else:
                logging.info("%s: TCP/%s already correct", hostname, port)
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
    logging.info("Creating %s new disk(s) in NetBox...", len(disks_to_create))
    nb_post(VDISK_ENDPOINT, disks_to_create)


def bulk_update_disks(disks_to_update):
    if not disks_to_update:
        return
    logging.info("Updating %s disk(s) in NetBox...", len(disks_to_update))
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
                logging.info(
                    "Disk '%s' on VM '%s' is already correct.",
                    disk_name,
                    vm_name,
                )
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
        logging.info(
            "REMOVED disk '%s' (id=%s) from VM '%s' – no longer in Zabbix.",
            disk_name,
            disk_id,
            vm_name,
        )


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
        logging.info("Updating VM ID %s with missing resource fields.", vm_id)
    elif current_memory == new_memory and current_vcpus == new_vcpus:
        logging.info(
            "VM ID %s: resources already correct (memory=%s, vcpus=%s).",
            vm_id,
            current_memory,
            current_vcpus,
        )
        return

    nb_patch(f"{VM_ENDPOINT}{vm_id}/", payload)
    logging.info(
        "UPDATED VM ID %s: memory=%s MB, vcpus=%s", vm_id, new_memory, new_vcpus
    )



# OS + EOL helpers


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

    # Windows Server (future-proof: any 4-digit year)
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
            resp = requests.get(
                url, headers={"Accept": "application/json"}, verify=VERIFY_SSL
            )
            resp.raise_for_status()
            data = resp.json()
            for entry in data:
                if entry.get("cycle") == os_version:
                    eol = entry.get("eol")
                    return "Still Supported" if not eol else eol
            logging.warning("SLES version %s not found in EOL data.", os_version)
            return "Unknown"

        else:
            url = f"{EOL_API_BASE}/{os_name}/{os_version}.json"
            resp = requests.get(
                url, headers={"Accept": "application/json"}, verify=VERIFY_SSL
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("eol", "Unknown")

    except Exception as exc:
        logging.warning(
            "Error fetching EOL info for %s %s: %s", os_name, os_version, exc
        )
        return "Unknown"


def update_vm_os(vm_record, new_os, os_eol):
    vm_id = vm_record.get("id")
    cf = vm_record.get("custom_fields", {}) or {}

    # If the fields are not present at all, assume they are not defined in NetBox
    if "operating_system" not in cf or "operating_system_EOL" not in cf:
        logging.warning(
            "VM ID %s: OS/EOL custom fields missing; skipping OS update.",
            vm_id,
        )
        return

    current_os = cf.get("operating_system")
    current_eol = cf.get("operating_system_EOL")

    if current_os == new_os and current_eol == os_eol:
        logging.info(
            "VM ID %s: OS/EOL already correct (OS='%s', EOL='%s').",
            vm_id,
            current_os,
            current_eol,
        )
        return

    payload = {
        "custom_fields": {
            "operating_system": new_os,
            "operating_system_EOL": os_eol,
        }
    }

    nb_patch(f"{VM_ENDPOINT}{vm_id}/", payload)
    logging.info(
        "UPDATED VM ID %s: operating_system='%s', operating_system_EOL='%s'",
        vm_id,
        new_os,
        os_eol,
    )



# Host inventory from Zabbix


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



# Orchestration


def process_host(host_inv):
    host_name = host_inv["host"]
    host_id = host_inv["host_id"]
    logging.info("=== Processing host %s (ID %s) ===", host_name, host_id)

    vm = find_vm_by_substring(host_name)
    if not vm:
        return

    # 1) OS + EOL
    os_value = host_inv.get("operating_system")
    os_vendor, os_version = parse_os_vendor_and_version(os_value or "")
    os_eol = get_os_eol(os_vendor, os_version) if os_vendor else "Unknown"
    try:
        update_vm_os(vm, os_value, os_eol)
    except Exception as exc:
        logging.warning(
            "%s: failed to update OS/EOL in NetBox: %s", host_name, exc
        )

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
        logging.warning(
            "Skipping resource update for %s: memory=%s, cores=%s",
            host_name,
            total_memory_gb,
            cores,
        )

    # 3) Disks
    disks = host_inv.get("disks") or {}
    if disks:
        update_disks_for_vm(vm, disks)
    else:
        logging.info("%s: no disk data to sync.", host_name)

    # 4) Listening services
    services_entries = get_listening_services_from_zabbix(host_id)
    if services_entries:
        update_services_for_vm(vm, services_entries)
    else:
        logging.info(
            "%s: no listening-services JSON found in Zabbix.", host_name
        )


def main() -> int:
    require_tokens()
    overall_ok = True

    for host_inv in collect_host_inventory():
        try:
            process_host(host_inv)
        except Exception as exc:
            logging.error("Failed processing %s: %s", host_inv.get("host"), exc)
            overall_ok = False

    return 0 if overall_ok else 1


if __name__ == "__main__":
    exit_code = 1
    try:
        exit_code = main()
    except Exception as exc:
        logging.error("Fatal error in main(): %s", exc)
        exit_code = 1
    finally:
        # Report to Zabbix: 1 = success, 0 = failure
        try:
            report_status_to_zabbix(exit_code == 0)
        except Exception as exc:
            logging.warning("Error while reporting status to Zabbix: %s", exc)

    sys.exit(exit_code)
