import threading
import time
from datetime import datetime, timedelta

from config import ZABBIX_REFRESH_SECONDS
from zabbix_integration import build_network_map
from netbox_integration import fetch_netbox_vms, fetch_netbox_services
from state import set_cached_map, set_netbox_data
from report_generator import generate_all_reports


def zabbix_worker():
    try:
        set_cached_map(build_network_map())
        print("[ZABBIX] Första uppdatering klar")
    except Exception as e:
        print("[ZABBIX ERROR]", e)

    while True:
        time.sleep(ZABBIX_REFRESH_SECONDS)
        try:
            set_cached_map(build_network_map())
            print(f"[ZABBIX] Uppdaterad {datetime.now().isoformat()}")
        except Exception as e:
            print("[ZABBIX ERROR]", e)


def netbox_worker():
    try:
        vms = fetch_netbox_vms()
        services = fetch_netbox_services()
        set_netbox_data(vms, services)
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
            vms = fetch_netbox_vms()
            services = fetch_netbox_services()
            set_netbox_data(vms, services)
            print(f"[NETBOX] Uppdaterad {datetime.now().isoformat()}")
        except Exception as e:
            print("[NETBOX ERROR]", e)


def report_worker():
    # initial run
    try:
        print("[REPORT] Första körning startar")
        generate_all_reports()
        print("[REPORT] Första körning klar")
    except Exception as e:
        print("[REPORT ERROR]", e)

    # run daily at 02:00
    while True:
        now = datetime.now()
        next_run = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        time.sleep((next_run - now).total_seconds())
        try:
            print("[REPORT] Schemalagd körning startar")
            generate_all_reports()
            print("[REPORT] Schemalagd körning klar")
        except Exception as e:
            print("[REPORT ERROR]", e)


def start_workers():
    threading.Thread(target=zabbix_worker, daemon=True).start()
    threading.Thread(target=netbox_worker, daemon=True).start()
    threading.Thread(target=report_worker, daemon=True).start()
