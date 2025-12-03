import math
import re
from typing import Any, Dict, List, Optional

from ..zabbix_client import call as zbx_call


def _convert_to_gb(bytes_str: str) -> Any:
    try:
        bytes_val = int(bytes_str)
        return math.ceil(bytes_val / (1024 ** 3))
    except (ValueError, TypeError):
        return "N/A"


def _get_all_host_groups() -> List[Dict[str, Any]]:
    return zbx_call(
        "hostgroup.get",
        {
            "output": ["groupid", "name"],
            "selectHosts": ["hostid"],
            "sortfield": "name",
        },
    )


def _get_disk_info_windows(host_id: str) -> Dict[str, Any]:
    """
    For Windows: search keys like
    vfs.fs.dependent.size[...,"total"]
    and return {<label>: size_gb}. 
    """
    disk_info: Dict[str, Any] = {}
    items = zbx_call(
        "item.get",
        {
            "hostids": host_id,
            "search": {"key_": "vfs.fs.dependent.size"},
            "output": ["key_", "lastvalue"],
        },
    )
    for item in items:
        key = item["key_"]
        value = item.get("lastvalue", "0")
        match = re.search(r'\[(.*?),total\]', key)
        if match:
            disk_label = match.group(1)
            disk_size_gb = _convert_to_gb(value)
            disk_info[disk_label] = disk_size_gb
    return disk_info


def _get_disk_info_linux(host_id: str) -> Dict[str, Any]:
    """
    For Linux: search vfs.fs.size[...,"total"], similar to original script. 
    """
    disk_info: Dict[str, Any] = {}
    items = zbx_call(
        "item.get",
        {
            "hostids": host_id,
            "search": {"key_": "vfs.fs.size"},
            "output": ["key_", "lastvalue"],
        },
    )
    for item in items:
        key = item["key_"]
        value = item.get("lastvalue", "0")
        match = re.search(r'\[(.*?),total\]', key)
        if match:
            disk_label = match.group(1)
            disk_size_gb = _convert_to_gb(value)
            disk_info[disk_label] = disk_size_gb
    return disk_info


def _get_item_value_by_name(host_id: str, item_name: str) -> str:
    items = zbx_call(
        "item.get",
        {
            "hostids": host_id,
            "filter": {"name": item_name},
            "output": ["lastvalue"],
        },
    )
    if items:
        return items[0].get("lastvalue", "N/A")
    return "N/A"


def _get_item_value_by_key(host_id: str, item_key: str) -> str:
    items = zbx_call(
        "item.get",
        {
            "hostids": host_id,
            "filter": {"key_": item_key},
            "output": ["lastvalue"],
        },
    )
    if items:
        return items[0].get("lastvalue", "N/A")
    return "N/A"


def _get_linux_os_pretty_name(host_id: str) -> str:
    return _get_item_value_by_name(host_id, "OSI PRETTY_NAME")


def get_host_info(
    group_ids: Optional[List[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Return server info per group (OS, memory, cores, disks), based on
    host_information-Pretty _Name.py but as data instead of files. 

    Returns:
    {
      "<group_name>": [
        {
          "hostid": str,
          "host": str,
          "operating_system": str,
          "total_memory_gb": int or "N/A",
          "cores": str/int,
          "disks": {mount_or_label: size_gb, ...}
        },
        ...
      ],
      ...
    }
    """
    if group_ids is None:
        groups = _get_all_host_groups()
    else:
        groups = zbx_call(
            "hostgroup.get",
            {
                "output": ["groupid", "name"],
                "groupids": group_ids,
                "selectHosts": ["hostid"],
            },
        )

    os_key = "system.sw.os"
    memory_key = "vm.memory.size[total]"

    result: Dict[str, List[Dict[str, Any]]] = {}

    for group in groups:
        group_id = group["groupid"]
        group_name = group["name"]
        hosts = group.get("hosts") or zbx_call(
            "host.get",
            {
                "groupids": group_id,
                "output": ["hostid", "host"],
            },
        )

        group_data: List[Dict[str, Any]] = []

        for host in hosts:
            host_id = host["hostid"]

            host_info = zbx_call(
                "host.get",
                {
                    "hostids": host_id,
                    "output": ["host"],
                },
            )
            host_name = host_info[0]["host"] if host_info else "Unknown"

            os_version = _get_item_value_by_key(host_id, os_key) or "Unknown"
            if "linux" in group_name.lower() or "linux" in os_version.lower():
                os_version = _get_linux_os_pretty_name(host_id) or os_version

            memory_bytes = _get_item_value_by_key(host_id, memory_key)
            memory_gb = _convert_to_gb(memory_bytes)

            if "windows" in group_name.lower() or "windows" in os_version.lower():
                cores_key = 'wmi.get[root/cimv2,"Select NumberOfLogicalProcessors from Win32_ComputerSystem"]'
                disks = _get_disk_info_windows(host_id)
            elif "linux" in group_name.lower() or "linux" in os_version.lower():
                cores_key = "system.cpu.num"
                disks = _get_disk_info_linux(host_id)
            else:
                cores_key = None
                disks = {}

            if cores_key:
                cores = _get_item_value_by_key(host_id, cores_key)
            else:
                cores = "Unknown"

            group_data.append(
                {
                    "hostid": host_id,
                    "host": host_name,
                    "operating_system": os_version,
                    "total_memory_gb": memory_gb,
                    "cores": cores,
                    "disks": disks,
                }
            )

        result[group_name] = group_data

    return result
