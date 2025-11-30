import threading
import time
from datetime import datetime, timedelta

from config import ZABBIX_REFRESH_SECONDS
from zabbix_integration import build_network_map
from netbox_integration import fetch_netbox_vms, fetch_netbox_services
from state import set_cached_map, set_netbox_data
from report_generator import generate_all_reports
from log import get_logger

logger = get_logger(__name__)


def zabbix_worker():
    # First run
    try:
        logger.info("Zabbix worker: initial update started")
        set_cached_map(build_network_map())
        logger.info("Zabbix worker: initial update completed")
    except Exception as e:
        logger.exception("Zabbix worker: initial update FAILED: %s", e)

    # Periodic refresh
    while True:
        time.sleep(ZABBIX_REFRESH_SECONDS)
        try:
            logger.info("Zabbix worker: scheduled update started")
            set_cached_map(build_network_map())
            logger.info("Zabbix worker: scheduled update completed at %s", datetime.now().isoformat())
        except Exception as e:
            logger.exception("Zabbix worker: scheduled update FAILED: %s", e)


def netbox_worker():
    # First run
    try:
        logger.info("NetBox worker: initial update started")
        vms = fetch_netbox_vms()
        services = fetch_netbox_services()
        set_netbox_data(vms, services)
        logger.info("NetBox worker: initial update completed")
    except Exception as e:
        logger.exception("NetBox worker: initial update FAILED: %s", e)

    # Daily at 01:00
    while True:
        now = datetime.now()
        nxt = now.replace(hour=1, minute=0, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        sleep_seconds = (nxt - now).total_seconds()
        logger.info("NetBox worker: sleeping %.0f seconds until next run at %s", sleep_seconds, nxt.isoformat())
        time.sleep(sleep_seconds)

        try:
            logger.info("NetBox worker: scheduled update started")
            vms = fetch_netbox_vms()
            services = fetch_netbox_services()
            set_netbox_data(vms, services)
            logger.info("NetBox worker: scheduled update completed at %s", datetime.now().isoformat())
        except Exception as e:
            logger.exception("NetBox worker: scheduled update FAILED: %s", e)


def report_worker():
    # First run
    try:
        logger.info("Report worker: initial report generation started")
        generate_all_reports()
        logger.info("Report worker: initial report generation completed")
    except Exception as e:
        logger.exception("Report worker: initial report generation FAILED: %s", e)

    # Daily at 02:00
    while True:
        now = datetime.now()
        next_run = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        sleep_seconds = (next_run - now).total_seconds()
        logger.info("Report worker: sleeping %.0f seconds until next run at %s", sleep_seconds, next_run.isoformat())
        time.sleep(sleep_seconds)

        try:
            logger.info("Report worker: scheduled report generation started")
            generate_all_reports()
            logger.info("Report worker: scheduled report generation completed at %s", datetime.now().isoformat())
        except Exception as e:
            logger.exception("Report worker: scheduled report generation FAILED: %s", e)


def start_workers():
    logger.info("Starting background workers (Zabbix, NetBox, Report)")
    threading.Thread(target=zabbix_worker, daemon=True).start()
    threading.Thread(target=netbox_worker, daemon=True).start()
    threading.Thread(target=report_worker, daemon=True).start()
