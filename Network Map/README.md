# Zabbix Network Map

En webbapplikation som visualiserar TCP nätverkstrafik insamlad via Zabbix-agenter och enrichad med data från NetBox. Applikationen genererar även automatiska 30-dagarsrapporter (Excel/CSV/DrawIO).

# Länkar
WEBSITE-URL/api/status
WEBSITE-URL/api/network_map
WEBSITE-URL/logs.html

## Arkitektur

- Backend:
  - Python 3, FastAPI, Uvicorn
  - Moduler:
    - `main.py` – entrypoint, initierar FastAPI, routrar och mountar statiska filer.
    - `config.py` – grundkonfiguration (Zabbix/NetBox-URL, tokens, refreshinterval).
    - `helpers.py` – hjälpfunktioner (t.ex. miljöklassificering, IP-typer).
    - `state.py` – delad applikationsstate med trådsäkra lås (network map-cache, NetBox-cache, problem-lista).
    - `zabbix_integration.py` – Zabbix API-anrop, byggnation av 24h-nätverkskartan.
    - `netbox_integration.py` – NetBox API-anrop (VM:ar, tjänster).
    - `workers.py` – bakgrundstrådar för Zabbix, NetBox och rapportgenerering.
    - `routes_core.py` – API-endpoints för status, nätverkskarta, rapportlistning och zip-nedladdning.
    - `routes_netbox.py` – API-endpoints för NetBox-VM och tjänster.
    - `routes_zabbix.py` – API-endpoints för Zabbix-webhook (problem/resolve) och aktiv problemlista.
    - `report_config.py` – rapportkonfiguration, cachekatalog, tidsfönster (30 dagar).
    - `report_data.py` – hämtning av historik från Zabbix och IP→host-uppslag inklusive NetBox-cache.
    - `report_builders.py` – skapande av `.xlsx`, `.csv` och `.drawio`.
    - `report_generator.py` – wrapper-funktion `generate_all_reports()` som kör alla rapporttyper.

- Frontend:
  - Statiska filer i `/opt/network_map/static`:
    - `index.html` – SPA-HTML, formkontroller, paneler för sammanfattning och NetBox-info.
    - `styles.css` – styling inklusive dark-mode, paneler, layouts.
    - `app.js` – all logik för att hämta data från `/api/*`, rita cytoscape-grafen, filtrering, NetBox-panel, summariseringsfönster och nedladdning av rapport-zip.
    - 3:e partsresurser: `bootstrap.min.css`, `cytoscape.min.js`, `cytoscape-cose-bilkent.js`.

- Reverse proxy:
  - Nginx terminering av HTTPS, statisk leverans av SPA, proxy för `/api/*` till Uvicorn.

## Funktioner

- Hämtar 24h nätverksdata från Zabbix var 30:e minut (standard) och bygger en interaktiv graf.
- Färgkodar noder baserat på miljö (prod/dev/test/qa/unknown/external).
- Filtrering i UI:
  - Source/dest (delsträng).
  - Portar (enskilda, listor, intervall).
  - Exkludera publika IP.
  - Exkludera IP/CIDR/intervall.
- Klick på nod:
  - Highlight av inkommande/utgående edges.
  - Sammanfattningsruta för all trafik till/från noden (med stöd för include/exclude/filter på host/port).
  - NetBox-inforuta med:
    - CPU, RAM, disk
    - OS, EOL, patchfönster
    - Roll, HA-server, tjänster, länk till VM i NetBox.

## Rapporter (30 dagar)

- Integrerad rapportmotor (inga cronjobs behövs):
  - `workers.py` startar `report_worker` vid app-start.
  - `report_worker` kör `generate_all_reports()`:
    - vid uppstart
    - schemalagt dagligen (standard 02:00).
- Rapporter skapas i `/opt/network_map/reports`:
  - `network_blueprint_summary*.xlsx` – global översikt.
  - `network_blueprint_per_host*.xlsx` – per host.
  - `network_blueprint_gephi*.csv` – import till Gephi.
  - `network_blueprint_per_host*.drawio` – visuella per-host-diagram för DrawIO.
- 30-dagars cache:
  - Zabbix-historik cachas per itemid/dygn på disk i `reports/cache`.
  - Endast nya dagar hämtas, äldre än tidsfönstret rensas bort.

## Installation (kortversion)

Se `installations instruktion.txt` för detaljer.

1. Konfigurera Zabbix-agenter (Linux/Windows) med scripts och UserParameters.
2. Skapa `/opt/network_map` och underkataloger (`static`, `reports`).
3. Installera Pythonberoenden: `fastapi`, `uvicorn`, `requests`, `openpyxl`, `networkx` m.fl.
4. Kopiera alla `.py`-filer och statiska resurser till `/opt/network_map`.
5. Skapa systemd-tjänsten `network_map.service` för Uvicorn.
6. Skapa Nginx-konfiguration (`network_map.conf`) och peka på SPA-root `/opt/network_map/static` samt proxya `/api/*` till `127.0.0.1:8000`.
7. Starta/aktivera tjänsterna och testa via `https://<server_name>/`.

## Drift & Anpassning

- Ändra intervall för Zabbix/NetBox/rapport-workers i `workers.py` och `config.py`.
- Anpassa färger, layout och filterlogik i `app.js` och `styles.css`.
- Lägga till fler API-rutter genom att utöka `routes_*.py`.
- All konfiguration är hårdkodad i `config.py` i denna version (miljöspecifika värden kan flyttas till miljövariabler senare vid behov).
<br/>
<br/>
<br/>
### Screenshots

![Network Map Overview]([Network%20Map/Network_Map_Pictures/1.jpg](https://github.com/Keberneth/Zabbix-Extensions-Apps/blob/main/Network%20Map/Network_Map_Pictures/1.jpg))

![Node Details Popup](Network%20Map/Network_Map_Pictures/2.jpg)

![Filters and Search](Network%20Map/Network_Map_Pictures/3.jpg)

![Report Export Options](Network%20Map/Network_Map_Pictures/4.jpg)

![Draw.io Example](Network%20Map/Network_Map_Pictures/drawio.jpg)
