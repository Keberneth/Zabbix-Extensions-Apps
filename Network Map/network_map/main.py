import os
import json
import time
import threading
import ipaddress
import warnings
import urllib3
import requests
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import zipfile
import io

# --- KONFIGURATION ---
ZABBIX_URL             = "https://zabbix.example.se/api_jsonrpc.php"
ZABBIX_TOKEN           = "this_is_a_fake_token_for_example_purposes"
NETBOX_URL             = "https://netbox.example.se"
NETBOX_TOKEN           = "this_is_a_fake_token_for_example_purposes"
ZABBIX_REFRESH_SECONDS = 30 * 60
REPORT_DIR             = "/opt/network_map/reports"

PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
]

ENV_COLOR_MAP = {
    "prod": "#007bff",
    "dev": "#28a745",
    "test": "#fd7e14",
    "qa": "#6f42c1",
    "unknown": "#6c757d",
    "external": "#ff3366",
    "internal-unknown": "#999999"
}

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.simplefilter("ignore", urllib3.exceptions.SubjectAltNameWarning)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

cached_map      = {"nodes": [], "edges": []}
last_updated    = 0
netbox_vms      = {}
netbox_services = []
active_problems = set()
name_to_vm      = {}

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/reports", StaticFiles(directory=REPORT_DIR), name="reports")

@app.get("/")
def serve_index():
    return FileResponse("static/index.html")

@app.get("/api/status")
def api_status():
    return {"last_updated": last_updated}

@app.get("/api/network_map")
def api_network_map():
    return cached_map

@app.get("/api/netbox/vm")
def api_vm_by_name(name: str):
    for vm in netbox_vms.values():
        if vm.get("name") == name or vm.get("display") == name:
            return vm
    raise HTTPException(status_code=404, detail="VM not found")

@app.get("/api/netbox/services-by-vm")
def api_services_by_vm(name: str):
    return [svc for svc in netbox_services if svc.get("virtual_machine") and (svc["virtual_machine"].get("name") == name or svc["virtual_machine"].get("display") == name)]

@app.get("/api/reports")
def list_reports():
    report_dir = Path(REPORT_DIR)
    if not report_dir.exists():
        raise HTTPException(status_code=500, detail="Report directory not found")
    files = []
    for file in report_dir.iterdir():
        if file.suffix.lower() in [".csv", ".xlsx", ".drawio"]:
            mtime = datetime.fromtimestamp(file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            files.append({"name": file.name, "mtime": mtime})
    return files

@app.post("/api/webhook/zabbix_event")
async def zabbix_event(payload: dict):
    event_type = payload.get("event")
    server = payload.get("server")
    if not event_type or not server:
        return {"status": "ignored"}
    server = str(server)
    if event_type.lower() == "problem":
        active_problems.add(server)
    elif event_type.lower() == "resolve":
        active_problems.discard(server)
    return {"status": "ok"}

@app.get("/api/problems")
def get_problems():
    return {"problems": list(active_problems)}

def classify_env(name: str) -> str:
    if not name:
        return "unknown"
    val = name.lower()
    if any(k in val for k in ["prod", "prd", "produktion", "production"]): return "prod"
    if any(k in val for k in ["dev", "developer"]): return "dev"
    if any(k in val for k in ["test", "tst"]): return "test"
    if any(k in val for k in ["qa", "quality", "pre-prod", "preproduction", "pre production"]): return "qa"
    return "unknown"

def is_public_ip(ip: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip)
        return not any(ip_obj in net for net in PRIVATE_NETWORKS)
    except ValueError:
        return False

def is_internal_ip(ip: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip)
        return any(ip_obj in net for net in PRIVATE_NETWORKS)
    except ValueError:
        return False

def zabbix_api(method, params=None):
    payload = {"jsonrpc": "2.0", "method": method, "params": params or {}, "auth": ZABBIX_TOKEN, "id": 1}
    resp = requests.post(ZABBIX_URL, json=payload, headers={"Content-Type": "application/json-rpc"}, verify=False)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise Exception(data["error"])
    return data["result"]

def fetch_netbox_vms():
    vms = {}
    url = f"{NETBOX_URL}/api/virtualization/virtual-machines/"
    headers = {"Authorization": f"Token {NETBOX_TOKEN}"}
    params = {"limit": 1000}
    while url:
        r = requests.get(url, headers=headers, params=params, verify=False)
        r.raise_for_status()
        js = r.json()
        for vm in js.get("results", []):
            vms[str(vm["id"])] = vm
        url = js.get("next")
        params = None
    return vms

def fetch_netbox_services():
    svcs = []
    url = f"{NETBOX_URL}/api/ipam/services/"
    headers = {"Authorization": f"Token {NETBOX_TOKEN}"}
    params = {"limit": 1000}
    while url:
        r = requests.get(url, headers=headers, params=params, verify=False)
        r.raise_for_status()
        js = r.json()
        svcs.extend(js.get("results", []))
        url = js.get("next")
        params = None
    return svcs

def get_ip_maps():
    hosts = zabbix_api("host.get", {"output": ["host"], "selectInterfaces": ["ip"], "filter": {"status": 0}})
    ip2host, host2ip = {}, {}
    for h in hosts:
        name = h["host"]
        for iface in h.get("interfaces", []):
            ip = iface.get("ip")
            if ip:
                ip2host[ip] = name
                host2ip.setdefault(name, ip)
    try:
        for vm in fetch_netbox_vms().values():
            ip4 = vm.get("primary_ip4") and vm["primary_ip4"]["address"].split("/")[0]
            if ip4:
                display = vm.get("display") or vm.get("name")
                ip2host[ip4] = display
                host2ip.setdefault(display, ip4)
    except Exception:
        pass
    return ip2host, host2ip

def get_network_items():
    return zabbix_api("item.get", {
        "output": ["itemid"],
        "filter": {"name": ["linux-network-connections", "windows-network-connections"]},
        "selectHosts": ["host"]
    })

def get_history(itemid, time_from, time_till):
    return zabbix_api("history.get", {
        "output": "extend",
        "history": 4,
        "itemids": [itemid],
        "time_from": time_from,
        "time_till": time_till,
        "sortfield": "clock",
        "sortorder": "ASC",
        "limit": 100000
    })

def build_network_map():
    tf = int(time.time()) - 24 * 3600
    tt = int(time.time())
    ip2host, host2ip = get_ip_maps()
    edges_set, nodes = set(), set()
    for itm in get_network_items():
        itemid = itm["itemid"]
        history = get_history(itemid, tf, tt)
        for entry in history:
            try:
                conn = json.loads(entry["value"])
            except Exception:
                continue
            if not isinstance(conn, dict):
                continue
            incoming = conn.get("incomingconnections", [])
            outgoing = conn.get("outgoingconnections", [])
            for conn_list, direction in [(incoming, "in"), (outgoing, "out")]:
                if isinstance(conn_list, dict):
                    conn_list = [conn_list]
                elif not isinstance(conn_list, list):
                    continue
                for c in conn_list:
                    if not isinstance(c, dict):
                        continue
                    lip = c.get("localip")
                    rip = c.get("remoteip")
                    port = c.get("localport") or c.get("remoteport") or ""
                    if direction == "in":
                        src = ip2host.get(rip, rip)
                        dst = ip2host.get(lip, lip)
                    else:
                        src = ip2host.get(lip, lip)
                        dst = ip2host.get(rip, rip)
                    nodes.update([src, dst])
                    # Determine if it's a public IP
                    is_pub = True
                    try:
                        ipobj = ipaddress.ip_address(rip)
                        if any(ipobj in net for net in PRIVATE_NETWORKS):
                            is_pub = False
                    except Exception:
                        pass
                    edges_set.add((src, dst, port, is_pub))
    # Calculate node degrees
    degree = {n: 0 for n in nodes}
    for s, d, _, _ in edges_set:
        degree[s] += 1
        degree[d] += 1
    # Build nodes
    node_data = []
    for n in nodes:
        ip = host2ip.get(n, "")
        label = f"{n} ({ip})" if ip else n
        # Determine environment color
        role_name = name_to_vm.get(n, {}).get("role", {}).get("name", "")
        env = classify_env(role_name)
        color = ENV_COLOR_MAP["external"] if is_public_ip(ip) else ENV_COLOR_MAP.get(env, ENV_COLOR_MAP["internal-unknown"])
        node_data.append({
            "data": {
                "id": n,
                "label": label,
                "degree": degree[n],
                "ip": ip,
                "color": color
            }
        })
    # Build edges
    edge_data = []
    for s, d, p, isp in edges_set:
        edge_data.append({
            "data": {
                "source": s,
                "target": d,
                "label": f"port {p}" if p else "",
                "isPublic": isp,
                "srcIp": host2ip.get(s, ""),
                "dstIp": host2ip.get(d, "")
            }
        })
    return {
        "nodes": node_data,
        "edges": edge_data
    }


def zabbix_worker():
    global cached_map, last_updated
    try:
        cached_map = build_network_map()
        last_updated = int(time.time())
        print("[ZABBIX] Första uppdatering klar")
    except Exception as e:
        print("[ZABBIX ERROR]", e)
    while True:
        time.sleep(ZABBIX_REFRESH_SECONDS)
        try:
            cached_map = build_network_map()
            last_updated = int(time.time())
            print(f"[ZABBIX] Uppdaterad {datetime.now().isoformat()}")
        except Exception as e:
            print("[ZABBIX ERROR]", e)

def netbox_worker():
    global netbox_vms, netbox_services, name_to_vm
    try:
        netbox_vms      = fetch_netbox_vms()
        netbox_services = fetch_netbox_services()
        name_to_vm      = {vm["name"]: vm for vm in netbox_vms.values()}
        print("[NETBOX] Första uppdatering klar")
    except Exception as e:
        print("[NETBOX ERROR]", e)
    while True:
        now = datetime.now()
        nxt = now.replace(hour=1, minute=0, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        time.sleep((nxt - now).total_seconds())
        try:
            netbox_vms      = fetch_netbox_vms()
            netbox_services = fetch_netbox_services()
            name_to_vm      = {vm["name"]: vm for vm in netbox_vms.values()}
            print(f"[NETBOX] Uppdaterad {datetime.now().isoformat()}")
        except Exception as e:
            print("[NETBOX ERROR]", e)

@app.get("/api/reports/download_zip")
def download_reports_zip():
    report_dir = Path(REPORT_DIR)
    if not report_dir.exists():
        raise HTTPException(status_code=500, detail="Report directory not found")

    mem_zip = io.BytesIO()
    try:
        with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file in report_dir.iterdir():
                if file.suffix.lower() in [".csv", ".xlsx", ".drawio"]:
                    zf.write(file, arcname=file.name)
        mem_zip.seek(0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating zip file: {str(e)}")

    return StreamingResponse(mem_zip, media_type="application/zip", headers={
        "Content-Disposition": "attachment; filename=network_reports.zip"
    })

threading.Thread(target=zabbix_worker, daemon=True).start()
threading.Thread(target=netbox_worker, daemon=True).start()

