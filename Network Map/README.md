# Zabbix Network Map

A web application that visualizes TCP network traffic collected via Zabbix agents and enriched with data from NetBox. The application also generates automatic 30-day reports (Excel/CSV/DrawIO).

<big><string>Needed Zabbix plugin: windows_network_connections and linux_network_connections: <br>
https://github.com/Keberneth/Zabbix-Plugins
<br><br>
With related template:
<br>
Linux Network Map by Zabbix agent active.yaml
<br>
https://github.com/Keberneth/Zabbix-Templates/tree/main/OS/Linux
<br><br>
Windows Network Map by Zabbix agent active.yaml
<br>
https://github.com/Keberneth/Zabbix-Templates/tree/main/OS/Windows
<br>

# Links
WEBSITE-URL/api/status<br/>
WEBSITE-URL/api/network_map<br/>
WEBSITE-URL/logs.html<br/>
<br/>
## Architecture<br/>

- Backend:
  - Python 3, FastAPI, Uvicorn
  - Modules:
    - `main.py` – entry point, initializes FastAPI, routers, and mounts static files.
    - `config.py` – base configuration (Zabbix/NetBox URLs, tokens, refresh intervals).
    - `helpers.py` – helper functions (e.g. environment classification, IP types).
    - `state.py` – shared application state with thread-safe locks (network map cache, NetBox cache, problem list).
    - `zabbix_integration.py` – Zabbix API calls, builds the 24-hour network map.
    - `netbox_integration.py` – NetBox API calls (VMs, services).
    - `workers.py` – background threads for Zabbix, NetBox, and report generation.
    - `routes_core.py` – API endpoints for status, network map, report listing, and ZIP download.
    - `routes_netbox.py` – API endpoints for NetBox VMs and services.
    - `routes_zabbix.py` – API endpoints for Zabbix webhook (problem/resolve) and active problem list.
    - `report_config.py` – report configuration, cache directory, time window (30 days).
    - `report_data.py` – retrieval of history from Zabbix and IP→host lookups, including NetBox cache.
    - `report_builders.py` – creation of `.xlsx`, `.csv`, and `.drawio`.
    - `report_generator.py` – wrapper function `generate_all_reports()` that runs all report types.

- Frontend:
  - Static files in `/opt/network_map/static`:
    - `index.html` – SPA HTML, form controls, panels for summary and NetBox information.
    - `styles.css` – styling including dark mode, panels, and layouts.
    - `app.js` – all logic for fetching data from `/api/*`, rendering the Cytoscape graph, filtering, the NetBox panel, the summary window, and downloading the report ZIP.
    - Third-party resources: `bootstrap.min.css`, `cytoscape.min.js`, `cytoscape-cose-bilkent.js`.

- Reverse proxy:
  - Nginx terminates HTTPS, serves the SPA static files, and proxies `/api/*` to Uvicorn.

## Features

- Fetches 24-hour network data from Zabbix every 30 minutes (default) and builds an interactive graph.
- Color-codes nodes based on environment (prod/dev/test/qa/unknown/external).
- Filtering in the UI:
  - Source/destination (substring).
  - Ports (single values, lists, ranges).
  - Exclude public IPs.
  - Exclude IP/CIDR/ranges.
- Click on a node:
  - Highlights incoming/outgoing edges.
  - Summary box for all traffic to/from the node (with support for include/exclude/filter on host/port).
  - NetBox info box with:
    - CPU, RAM, disk
    - OS, EOL, patch window
    - Role, HA server, services, link to the VM in NetBox.

## Reports (30 days)

- Integrated report engine (no cron jobs required):
  - `workers.py` starts `report_worker` at app startup.
  - `report_worker` runs `generate_all_reports()`:
    - on startup
    - scheduled daily (default 02:00).
- Reports are created in `/opt/network_map/reports`:
  - `network_blueprint_summary*.xlsx` – global overview.
  - `network_blueprint_per_host*.xlsx` – per host.
  - `network_blueprint_gephi*.csv` – import into Gephi.
  - `network_blueprint_per_host*.drawio` – visual per-host diagrams for DrawIO.
- 30-day cache:
  - Zabbix history is cached per itemid/day on disk in `reports/cache`.
  - Only new days are fetched; data older than the time window is cleaned up.

## Installation (short version)

See `installations instruktion.txt` for details.

1. Configure Zabbix agents (Linux/Windows) with scripts and UserParameters.
2. Create `/opt/network_map` and subdirectories (`static`, `reports`).
3. Install Python dependencies: `fastapi`, `uvicorn`, `requests`, `openpyxl`, `networkx`, etc.
4. Copy all `.py` files and static resources to `/opt/network_map`.
5. Create the systemd service `network_map.service` for Uvicorn.
6. Create the Nginx configuration (`network_map.conf`) and point it to the SPA root `/opt/network_map/static`, and proxy `/api/*` to `127.0.0.1:8000`.
7. Start/enable the services and test via `https://<server_name>/`.

## Operations & Customization

- Change the intervals for Zabbix/NetBox/report workers in `workers.py` and `config.py`.
- Customize colors, layout, and filter logic in `app.js` and `styles.css`.
- Add more API routes by extending `routes_*.py`.
- All configuration is hardcoded in `config.py` in this version (environment-specific values can be moved to environment variables later if needed).
<br/>
<br/>
<br/>
### Screenshots

![Network Map Overview](https://raw.githubusercontent.com/Keberneth/Zabbix-Extensions-Apps/main/Network%20Map/Network_Map_Pictures/1.jpg)

![Node Details Popup](https://raw.githubusercontent.com/Keberneth/Zabbix-Extensions-Apps/main/Network%20Map/Network_Map_Pictures/2.jpg)

![Filters and Search](https://raw.githubusercontent.com/Keberneth/Zabbix-Extensions-Apps/main/Network%20Map/Network_Map_Pictures/3.jpg)

![Report Export Options](https://raw.githubusercontent.com/Keberneth/Zabbix-Extensions-Apps/main/Network%20Map/Network_Map_Pictures/4.jpg)

![Draw.io Example](https://raw.githubusercontent.com/Keberneth/Zabbix-Extensions-Apps/main/Network%20Map/Network_Map_Pictures/drawio.jpg)
