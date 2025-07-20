#!/usr/bin/env python3
"""
zbx_ai.py – Zabbix → LLM first-line run-book generator
––––––––––––––––––––––––––––––––––––––––––––––––––––––
• Enriches a Zabbix webhook with NetBox CMDB data
• Feeds the combined context to an Ollama model
• Saves the Markdown run-book as an HTML file
• Drops an acknowledgement back to the event
"""

import os
import re
import json
import urllib.parse
from datetime import datetime
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ─────────────────── Configuration ────────────────────

ZABBIX_API_URL   = "https://zabbix.example.se/api_jsonrpc.php"
ZABBIX_API_TOKEN = "this_is_a_test_token"

OLLAMA_URL   = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.2:1b"

NETBOX_URL   = "https://netbox.example.se"
NETBOX_TOKEN = "this_is_a_test_netbox_token"

WEB_HELP_DIR = "/usr/share/zabbix/ai/problems"
WEB_HELP_URL = "https://zbx-ai.example.se/problems"
LOGFILE      = os.path.join(WEB_HELP_DIR, "webhook_log.txt")

# ────────────── Global, centralised policy ─────────────

BASE_POLICY = """
You are a first-line troubleshooting assistant.

**Absolute rules (MUST never be broken)**  
•  **Never restart** a server, VM,   
•  **Never reinstall** software, services, application. or the OS.
•  Use only safe, reversible CLI/GUI checks:
   - `Start-Service`, `Get-Service`, `sc.exe query`
   - `systemctl start/status`, `journalctl`
   - log inspection, `netstat/ss`, performance counters, etc.  
•  Gather evidence and, if the quick fix fails, **escalate** to the customer’s
   2nd-line team with a tidy “escalation package”.

Always include:  
1️⃣  Quick, safe remediation attempt  
2️⃣  Verification step with expected output  
3️⃣  Evidence-gathering commands & log locations  
4️⃣  Hints for deeper analysis (perf, config, deps)  
5️⃣  Exact artefacts to attach when escalating  

Respond in **Markdown**.  Put commands in fenced code blocks.  Assume the reader
has administrative/root access to the host.
""".strip()

SYSTEM_PROMPT = BASE_POLICY

# ───────────────────── FastAPI app ─────────────────────

app = FastAPI()
handled_eventids: dict[str, dict[str, str]] = {}

# ─────────────────── Helper functions ──────────────────


def log(msg: str) -> None:
    """Write to console and to a rolling log file."""
    ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    os.makedirs(WEB_HELP_DIR, exist_ok=True)
    print(f"{ts} {msg}")
    with open(LOGFILE, "a", encoding="utf-8") as fh:
        fh.write(f"{ts} {msg}\n")


# ─────────────── NetBox convenience layer ──────────────

def _netbox_get(endpoint: str, params: dict) -> dict:
    hdrs = {"Authorization": f"Token {NETBOX_TOKEN}"}
    resp = requests.get(
        f"{NETBOX_URL}{endpoint}",
        headers=hdrs,
        params=params,
        timeout=10,
        verify=False  # ← Ignore self-signed cert
    )
    resp.raise_for_status()
    return resp.json()



def get_netbox_vm_info(hostname: str) -> dict | None:
    """Try to match hostname with NetBox VM entries by name/display (case-insensitive)."""
    data = _netbox_get("/api/virtualization/virtual-machines/", {
        "limit": 1000,  # increase in case many VMs exist
    })

    target = hostname.lower()

    for vm in data.get("results", []):
        name = vm.get("name", "").lower()
        display = vm.get("display", "").lower()

        if target in name or target in display:
            return vm

    return None

def get_netbox_vm_services(vm_id: int) -> list[dict]:
    data = _netbox_get("/api/ipam/services/",
                       {"virtual_machine_id": vm_id})
    return data.get("results", [])


def format_netbox_vm_info(vm: dict | None,
                          services: list[dict]) -> str:
    if not vm:
        return "No NetBox VM info found."

    lines: list[str] = []
    g = lambda f, *path: f
    lines.append(f"NetBox VM name: {vm.get('name','N/A')}")
    lines.append(f"Status: {vm.get('status', {}).get('label','N/A')}")
    lines.append(f"Site: {vm.get('site', {}).get('display','N/A')}")
    lines.append(f"Cluster: {vm.get('cluster', {}).get('display','N/A')}")
    lines.append(f"Role: {vm.get('role', {}).get('display','N/A')}")
    lines.append(f"Tenant: {vm.get('tenant', {}).get('display','N/A')}")
    lines.append(f"Platform: {vm.get('platform', {}).get('display','N/A')}")
    lines.append(f"Primary IP: {vm.get('primary_ip4',{}).get('address','N/A')}")
    lines.append(f"vCPUs: {vm.get('vcpus','N/A')}, "
                 f"RAM: {vm.get('memory','N/A')} MB, "
                 f"Disk: {vm.get('disk','N/A')} MB")

    os_field = vm.get("custom_fields", {}).get("operating_system")
    if os_field:
        lines.append(f"OS: {os_field}")

    if ha := vm.get("custom_fields", {}).get("ha_with_server"):
        ha_list = [i.get("display", i.get("name", str(i)))
                   if isinstance(i, dict) else str(i) for i in ha]
        lines.append(f"HA with server: {', '.join(ha_list)}")

    if svc := vm.get("custom_fields", {}).get("operations_services"):
        lines.append(f"Operations services: {', '.join(svc)}")

    if services:
        lines.append("Services listening on ports:")
        for s in services:
            name   = s.get("name", "N/A")
            proto  = s.get("protocol", {}).get("label", "N/A")
            ports  = ",".join(map(str, s.get("ports", [])))
            desc   = s.get("description", "")
            lines.append(f"  - {name} ({proto}/{ports}) {desc}")

    return "\n".join(lines)


# ──────────────── Zabbix API helpers ───────────────────

def zabbix_api(method: str, params: dict) -> dict:
    payload = {
        "jsonrpc": "2.0", "id": 1, "auth": ZABBIX_API_TOKEN,
        "method": method, "params": params
    }
    r = requests.post(
        ZABBIX_API_URL,
        json=payload,
        timeout=10,
        verify=False  # <- Disable cert validation for self-signed certs
    )
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"Zabbix API error: {data['error']}")
    return data["result"]



def get_host_id_by_name(hostname: str) -> str | None:
    res = zabbix_api("host.get", {
        "output": ["hostid"],
        "filter": {"host": [hostname]}
    })
    return res[0]["hostid"] if res else None


def get_os_type(host_id: str) -> str:
    res = zabbix_api("item.get", {
        "hostids": [host_id],
        "search": {"key_": "system.sw.os"},
        "output": ["lastvalue"]
    })
    lv = (res[0]["lastvalue"] if res else "").lower()
    if "windows" in lv:
        return "Windows"
    if any(k in lv for k in ("linux", "red hat", "ubuntu", "suse", "centos",
                             "rocky", "debian")):
        return "Linux"
    return "Unknown"


# ──────────────── Ollama wrapper ───────────────────────

def ollama_chat(user_prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        "stream": False,
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


# ─────────────── Formatting utilities ──────────────────

def safe_filename(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", text)


def save_html(eventid: str, host: str, trig: str,
              markdown_body: str) -> tuple[str, str]:
    """
    Write an HTML wrapper (markdown inside <pre>) and return (URL, path).
    """
    os.makedirs(WEB_HELP_DIR, exist_ok=True)
    fname = f"{eventid}_{safe_filename(host)}_{safe_filename(trig)}.html"
    fpath = os.path.join(WEB_HELP_DIR, fname)

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Run-book {eventid}</title>
<style>
body{{font-family:Arial,Helvetica,sans-serif;margin:20px}}
pre{{background:#f4f4f4;border:1px solid #ccc;padding:12px;overflow-x:auto}}
</style></head><body>
<h1>Troubleshooting run-book for event {eventid}</h1>
<pre>{markdown_body}</pre>
</body></html>
"""
    with open(fpath, "w", encoding="utf-8") as fh:
        fh.write(html)

    url = f"{WEB_HELP_URL}/{urllib.parse.quote(fname)}"
    return url, fpath


def acknowledge_event(eventid: str, link: str) -> None:
    params = {
        "eventids": [eventid],
        "action": 4,
        "message": f"Auto-generated troubleshooting help:\n\u27A1 {link}",
    }
    log("[DEBUG] Sending event.acknowledge:")
    log(json.dumps(params, indent=2))
    zabbix_api("event.acknowledge", params)


def delete_file(path: str) -> None:
    try:
        os.remove(path)
        log(f"[+] Deleted HTML file: {path}")
    except FileNotFoundError:
        pass
    except Exception as exc:
        log(f"[!] Could not delete {path}: {exc}")


# ───────────────────── Webhook ─────────────────────────

@app.post("/webhook")
async def zabbix_webhook(req: Request):
    """
    Main entry point for Zabbix → FastAPI webhook.
    """
    global handled_eventids

    log("[>] Webhook triggered!")

    try:
        raw = await req.json()
        msg = json.loads(raw["message"])  # Zabbix packs data as JSON string
        log("[ZABBIX RAW MESSAGE STRING]")
        log(json.dumps(msg, ensure_ascii=False))

        eventid = msg.get("eventid")
        trig    = msg.get("trigger_name")
        host    = msg.get("hostname")
        evalue  = msg.get("event_value", "1")     # 0 = RESOLVED

        if not all((eventid, trig, host)):
            return JSONResponse({"error": "Missing required fields"}, 400)

        # ───── Handle RESOLVED ─────
        if evalue == "0":
            if eventid in handled_eventids:
                delete_file(handled_eventids[eventid]["path"])
                handled_eventids.pop(eventid, None)
            return JSONResponse({"result": f"Resolved {eventid}"})

        # Ignore duplicate PROBLEM notification
        if eventid in handled_eventids:
            return JSONResponse({"result": f"Event {eventid} already handled"})

        log(f"[>] New Zabbix problem: {trig} (Event {eventid})")

        host_id = get_host_id_by_name(host)
        if not host_id:
            return JSONResponse({"error": f"No host ID for {host}"}, 404)

        os_tag = get_os_type(host_id)
        log(f"[DEBUG] Detected OS for {host}: {os_tag}")

        vm = get_netbox_vm_info(host)
        svcs = get_netbox_vm_services(vm["id"]) if vm else []
        nb_info = format_netbox_vm_info(vm, svcs)
        log(f"[DEBUG] NetBox info for {host}:\n{nb_info}")

        # ───── Build the user prompt (OS-specific bits) ─────
        os_lower = os_tag.lower()
        if "windows" in os_lower:
            user_prompt = (
                f"Problem: {trig}\n"
                f"Host OS: {os_tag}\n"
                f"CMDB / NetBox data:\n{nb_info}\n"
                "### Windows context\n"
                "Use PowerShell (`Get-Service`, `Start-Service`, `Get-WinEvent`, "
                "`sc.exe query`) and built-in tools only.\n"
            )
        elif any(k in os_lower for k in ("linux", "ubuntu", "redhat", "suse",
                                         "centos", "rocky", "debian")):
            user_prompt = (
                f"Problem: {trig}\n"
                f"Host OS: {os_tag}\n"
                f"CMDB / NetBox data:\n{nb_info}\n"
                "### Linux context\n"
                "Use `systemctl`, `journalctl -u <service>`, `ss -lntp`, "
                "`top/htop`, `df -h`, etc.\n"
            )
        else:
            user_prompt = (
                f"Problem: {trig}\n"
                f"Host OS: {os_tag}\n"
                f"CMDB / NetBox data:\n{nb_info}\n"
                "### Generic host\n"
                "Use neutral checks (process list, open ports, log files).\n"
            )

        # ───── Query Ollama ─────
        md_runbook = ollama_chat(user_prompt)

        # ───── Persist & acknowledge ─────
        link, path = save_html(eventid, host, trig, md_runbook)
        acknowledge_event(eventid, link)
        handled_eventids[eventid] = {"path": path, "link": link}

        return JSONResponse({"result": "OK", "link": link})

    except Exception as exc:
        log(f"[!] Webhook processing failed: {exc}")
        return JSONResponse({"error": str(exc)}, 500)

