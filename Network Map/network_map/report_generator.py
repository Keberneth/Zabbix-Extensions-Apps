from report_data import (
    cleanup_history_cache,
    get_all_hosts_ip_map,
    get_network_connection_items,
    parse_history_connections,
    filter_internal,
    filter_public,
)
from report_builders import (
    write_summary_excel,
    write_per_host_excel,
    write_gephi_csv,
    build_drawio_per_host,
)


def generate_all_reports() -> None:
    """
    Orchestrates the full 30-day report generation:
    - cleans cache
    - fetches IP/host map and items
    - parses history
    - writes summary/per-host/CSV/DrawIO for:
      * all connections
      * internal-only
      * public-only
    """
    print("[REPORT] Generating reports (30-day window)...")
    cleanup_history_cache()
    ip_map = get_all_hosts_ip_map()
    items = get_network_connection_items()
    if not items:
        print("[REPORT] No network-connection items found.")
        return

    rows = parse_history_connections(items, ip_map)

    # all rows
    write_summary_excel(rows, suffix="")
    write_per_host_excel(rows, suffix="")
    write_gephi_csv(rows, suffix="")
    build_drawio_per_host(rows, suffix="")

    # internal-only
    internal_rows = filter_internal(rows)
    write_summary_excel(internal_rows, suffix="_internal_ip")
    write_per_host_excel(internal_rows, suffix="_internal_ip")
    write_gephi_csv(internal_rows, suffix="_internal_ip")
    build_drawio_per_host(internal_rows, suffix="_internal_ip")

    # public-only
    public_rows = filter_public(rows)
    write_summary_excel(public_rows, suffix="_public_ip")
    write_per_host_excel(public_rows, suffix="_public_ip")
    write_gephi_csv(public_rows, suffix="_public_ip")
    build_drawio_per_host(public_rows, suffix="_public_ip")

    print("[REPORT] Report generation complete.")
