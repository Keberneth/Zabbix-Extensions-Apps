# Network Map – Översikt

## Förutsättningar

- Zabbix server och Zabbix-agenter (Linux/Windows) är driftsatta.
- NetBox är driftsatt och tillgänglig.
- Zabbix-agenterna har script och UserParameter konfigurerade för att samla in nätverksanslutningar (se installationsinstruktionerna).

## Datainsamling

### Zabbix-agenter (Linux/Windows)

På varje övervakad server:
- Linux:
  - Script: `/etc/zabbix/scripts/linux-network-connections.sh`
  - Gör scriptet exekverbart:
    - `chmod +x /etc/zabbix/scripts/linux-network-connections.sh`
  - UserParameter:
    - `/etc/zabbix/zabbix_agentd.d/linux-network-connections-param.conf`
    - `UserParameter=linux-network-connections,/etc/zabbix/scripts/linux-network-connections.sh`

- Windows:
  - Script: `C:\Program Files\Zabbix Agent 2\scripts\windows-network-connections.ps1`
  - UserParameter-fil:
    - `C:\Program Files\Zabbix Agent 2\zabbix_agent2.d\windows-network-connections-param.conf`
    - `UserParameter=windows-network-connections,powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Program Files\Zabbix Agent 2\scripts\windows-network-connections.ps1"`

Zabbix-templaten “linux-network-connections” och “windows-network-connections” ska importeras och kopplas till relevanta hosts.

## Network Map-applikationen

### Översikt

- Backend: FastAPI-applikation (Uvicorn) med flera moduler:
  - `main.py` (entrypoint + routrar)
  - `config.py`, `helpers.py`, `state.py`
  - `zabbix_integration.py`, `netbox_integration.py`
  - `workers.py`
  - `routes_core.py`, `routes_netbox.py`, `routes_zabbix.py`
  - `report_config.py`, `report_data.py`, `report_builders.py`, `report_generator.py`
- Frontend: Single Page Application (SPA) i `/opt/network_map/static`:
  - `static/index.html`
  - `static/styles.css`
  - `static/app.js`
  - samt t.ex. `bootstrap.min.css`, `cytoscape.min.js`, `cytoscape-cose-bilkent.js`.

### Nätverkskarta (24 timmar)

- Applikationen hämtar 24 timmar av nätverksdata från Zabbix var 30:e minut via en bakgrundstråd.
- Intervall och beteende kan justeras i `config.py` (t.ex. `ZABBIX_REFRESH_SECONDS`) och i `workers.py`.

### Rapportgenerering (30 dagar, integrerad)

- Rapportlogiken (`network-map-report`) är integrerad i applikationen via:
  - `report_config.py` – inställningar, cache, tidsfönster (30 dagar).
  - `report_data.py` – hämtning av Zabbix-historik och NetBox-uppslag, inkl. 30-dagars cache på disk.
  - `report_builders.py` – generering av `.xlsx`, `.csv` och `.drawio`.
  - `report_generator.py` – orkestrerar alla rapporter.
- Bakgrundstråden `report_worker` i `workers.py` kör `generate_all_reports()` en gång vid start och därefter schemalagt (standard: dagligen runt 02:00).
- Rapporter sparas i:
  - `/opt/network_map/reports`
- Ingen separat cronjob eller fristående `network-map-report.py` behövs längre.

# Manuellt skapoa rapporter
python3.12 -c "from report_generator import generate_all_reports; generate_all_reports()"

## NetBox-integration

- En bakgrundstråd (`netbox_worker`) i `workers.py` uppdaterar NetBox-data (VM:ar och tjänster) återkommande (som standard 1 gång per dygn).
- Kopplar ihop:
  - Zabbix-hostnamn / IP-adresser
  - NetBox VMs, roller, OS, EOL, patchfönster och tjänster.

## Filtrering i webbappen

I webbgränssnittet kan du filtrera nätverksgrafen via:

- **Source / Dest**:
  - Textmatchning på nod-id (delsträng).
- **Port**:
  - Enskild port: `443`
  - Flera portar: `80,443,8443`
  - Portintervall: `21-22` eller `1-10000`
- **Exkludera publika IP**:
  - Checkbox som filtrerar bort kanter där remote IP är publik.
- **IP/CIDR/intervall att exkludera**:
  - Exakt IP: `192.168.1.10`
  - CIDR: `10.0.0.0/16`
  - Intervall: `192.168.1.0-192.168.1.68`
  - Flera värden kan separeras med komma.

## NetBox- och trafikdetaljer

- Klicka på en nod/host i kartan för att:
  - Visa NetBox-information (CPU, RAM, disk, roll, HA, OS, EOL, tjänster m.m.) i en panel längst ned till höger.
  - Visa alla inkommande och utgående anslutningar för hosten i en sammanfattningsruta längst ned till vänster.
- Trafikfönstret kan filtreras med:
  - Inkludering och exkludering med `!`, t.ex.:
    - `!80,443` för att exkludera port 80 och 443.
  - Intervall, t.ex. `1-1024` eller kombinationer: `22,80-90,!8080`.

## Rapporter

- Applikationen genererar löpande 30-dagars rapporter baserat på all Zabbix-historik:
  - Sammanställningsfiler (`network_blueprint_summary*.xlsx`)
  - Per-host-filer (`network_blueprint_per_host*.xlsx`)
  - Gephi-CSV (`network_blueprint_gephi*.csv`)
  - DrawIO-filer (`network_blueprint_per_host*.drawio`)
- Rapporter finns för:
  - Alla anslutningar.
  - Endast interna IP → interna IP.
  - Endast anslutningar mot publika IP.
