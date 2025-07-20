#!/usr/bin/env python3
import os
import re
import json
import urllib.parse
import requests
import time
from datetime import datetime, date
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# --- KONFIGURATION -----------------------------------------------------------
ZABBIX_API_URL = "https://zabbix.example.se/api_jsonrpc.php"
ZABBIX_API_TOKEN = "this_is_a_test_token_1234567890abcdefg"

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL_PRIMARY   = "gpt-4o-mini"
OPENAI_MODEL_FALLBACK  = "gpt-3.5-turbo"
OPENAI_API_KEY = "this_is_a_test_openai_key_1234567890abcdefg"

WEB_HELP_DIR = "/usr/share/zabbix/ai/"
WEB_HELP_URL  = "https://zabbix.example.se"
LOGFILE       = os.path.join(WEB_HELP_DIR, "webhook_log.txt")
TOKEN_USAGE_FILE = os.path.join(WEB_HELP_DIR, "token_usage.log")

app = FastAPI()
handled_eventids: dict[str, dict] = {}
token_stats: dict[str, dict] = {}
last_logged_date: date = date.today()

# -----------------------------------------------------------------------------
# Hjälpfunktioner                                                               
# -----------------------------------------------------------------------------

def log(msg: str):
    ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    full = f"{ts} {msg}"
    print(full)
    os.makedirs(WEB_HELP_DIR, exist_ok=True)
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(full + "\n")

def zabbix_api(method: str, params: dict):
    payload = {
        "jsonrpc": "2.0",
        "method" : method,
        "params" : params,
        "auth"   : ZABBIX_API_TOKEN,
        "id"     : 1,
    }
    r = requests.post(ZABBIX_API_URL, headers={"Content-Type": "application/json"}, json=payload)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"Zabbix API error: {json.dumps(data['error'])}")
    return data.get("result")

# -- NY: Hämta operativsystem --------------------------------------------------

def get_host_os(hostname: str) -> str:
    """Returnera senaste värdet för item-key *system.sw.os* för angiven host."""
    try:
        hosts = zabbix_api("host.get", {
            "filter": {"host": [hostname]},
            "output": ["hostid"],
        })
        if not hosts:
            log(f"[!] Host '{hostname}' hittades inte i Zabbix")
            return "unknown"
        hostid = hosts[0]["hostid"]
        items = zabbix_api("item.get", {
            "hostids": [hostid],
            "search": {"key_": "system.sw.os"},
            "output": ["lastvalue"],
        })
        if items:
            return items[0].get("lastvalue", "").strip() or "unknown"
        log(f"[!] 'system.sw.os' saknas för hostid {hostid}")
        return "unknown"
    except Exception as e:
        log(f"[!] get_host_os() fel: {e}")
        return "unknown"

# -----------------------------------------------------------------------------
# OpenAI-anrop                                                                  
# -----------------------------------------------------------------------------

def call_openai_model(model: str, prompt: str):
    global token_stats, last_logged_date

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }

    payload = {
        "model": model,
        "messages": prompt,
        "temperature": 0.3,
        "stream": False,
    }

    for attempt in range(3):
        try:
            r = requests.post(OPENAI_API_URL, headers=headers, json=payload)
            if r.status_code == 429:
                log(f"[!] 429 på modell {model} (försök {attempt+1})")
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

    data = r.json()
    if data.get("error", {}).get("code") == "insufficient_quota":
        raise RuntimeError("OpenAI quota exceeded")

    usage = data.get("usage", {})
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        token_stats.setdefault(model, {"prompt":0, "completion":0, "total":0})
    token_stats[model]["prompt"]     += usage.get("prompt_tokens", 0)
    token_stats[model]["completion"] += usage.get("completion_tokens", 0)
    token_stats[model]["total"]      += usage.get("total_tokens", 0)

    today = date.today()
    if today != last_logged_date:
        with open(TOKEN_USAGE_FILE, "a", encoding="utf-8") as f:
            for m, stat in token_stats.items():
                f.write(f"{last_logged_date} {m} prompt={stat['prompt']} completion={stat['completion']} total={stat['total']}\n")
        token_stats.clear()
        last_logged_date = today

    return data["choices"][0]["message"]["content"].strip()

# -----------------------------------------------------------------------------
# Generera felsökningsförslag                                                   
# -----------------------------------------------------------------------------

def generate_troubleshooting_advice(trigger_desc: str, os_version: str) -> str:
    user_prompt = [
        {"role": "system", "content": "You are a troubleshooting assistant. Provide clear and structured troubleshooting advice."},
        {"role": "user",   "content": (
            f"A server reports: {trigger_desc}.\n"
            f"The host runs: {os_version}.\n"
            "Suggest step-by-step troubleshooting including relevant CMD/PowerShell or shell commands and which logs/journals to inspect." )},
    ]

    try:
        return call_openai_model(OPENAI_MODEL_PRIMARY, user_prompt)
    except RuntimeError as e:
        if "quota" in str(e).lower():
            log("[!] Skipping fallback: quota exceeded.")
            return "OpenAI quota exceeded. No troubleshooting advice available."
        log(f"[!] Primary model misslyckades: {e} – fall back till {OPENAI_MODEL_FALLBACK}")
        return call_openai_model(OPENAI_MODEL_FALLBACK, user_prompt)

# -----------------------------------------------------------------------------
# Diverse småhjälpare                                                          
# -----------------------------------------------------------------------------

def clean_suggestion(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

def safe_filename(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", text)

def save_html(eventid: str, host: str, trigger: str, suggestion: str):
    os.makedirs(WEB_HELP_DIR, exist_ok=True)
    filename = f"{eventid}_{safe_filename(host)}_{safe_filename(trigger)}.html"
    filepath = os.path.join(WEB_HELP_DIR, filename)

    html = f"""<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'><title>Help {eventid}</title><style>body{{font-family:Arial;padding:20px}}pre{{background:#f4f4f4;padding:10px;border:1px solid #ccc;overflow-x:auto}}</style></head><body><h1>Troubleshooting Help for Event {eventid}</h1><pre>{suggestion}</pre></body></html>"""
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(html)
    return f"{WEB_HELP_URL}/{urllib.parse.quote(filename)}", filepath

def post_message_link(eventid: str, help_link: str):
    try:
        zabbix_api("event.acknowledge", {
            "eventids": [eventid],
            "message" : f"Auto-generated troubleshooting help:\n➡ {help_link}",
            "action"  : 4,
        })
    except Exception as e:
        log(f"[!] Kunde inte skicka acknowledge: {e}")

def remove_html(path: str):
    try:
        os.remove(path)
        log(f"[+] Deleted {path}")
    except Exception as e:
        log(f"[!] Failed to delete {path}: {e}")

# -----------------------------------------------------------------------------
# FastAPI-endpoint                                                              
# -----------------------------------------------------------------------------

@app.post("/webhook")
async def zabbix_webhook(req: Request):
    global handled_eventids

    log("[>] Webhook triggered")
    raw = (await req.body()).decode("utf-8", "ignore")
    log(f"[DEBUG] Raw body: {raw}")

    try:
        payload = await req.json()
    except Exception as e:
        log(f"[!] JSON parse error: {e}")
        return JSONResponse({"error": "Invalid JSON"}, 400)

    try:
        message = json.loads(payload["message"])
    except Exception as e:
        log(f"[!] 'message' field decode error: {e}")
        return JSONResponse({"error": "Invalid 'message' content"}, 400)

    eventid      = message.get("eventid", "unknown")
    trigger_name = message.get("trigger_name", "unknown")
    host         = message.get("hostname", "unknown")
    event_value  = message.get("event_value", "1")  # 1=problem, 0=recovery

    if "unknown" in (eventid, trigger_name, host):
        return JSONResponse({"error": "Missing required fields"}, 400)

    # Återställning => ta bort HTML
    if event_value == "0":
        if eventid in handled_eventids:
            remove_html(handled_eventids[eventid]["filepath"])
            handled_eventids.pop(eventid, None)
            return JSONResponse({"result": f"Resolved {eventid}. HTML removed."})
        return JSONResponse({"result": f"Resolved {eventid} not tracked."})

    # Problem redan behandlat
    if eventid in handled_eventids:
        return JSONResponse({"result": f"Event {eventid} already handled."})

    log(f"[>] New Zabbix problem: {trigger_name} (Event ID: {eventid})")

    os_version = get_host_os(host)
    suggestion = generate_troubleshooting_advice(trigger_name, os_version)
    cleaned    = clean_suggestion(suggestion)

    link, path = save_html(eventid, host, trigger_name, cleaned)
    post_message_link(eventid, link)

    handled_eventids[eventid] = {"filepath": path, "help_link": link}
    return JSONResponse({"result": "OK", "link": link})
