"""Scheduled public DNS health checks with audit/notification hooks."""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from models.db import (
    get_dns_health_state,
    get_notification_settings,
    save_dns_health_state,
)
from services.cloudflare import build_setup_health, cf_is_configured
from services.mxroute import audit, mx_request_raw

logger = logging.getLogger(__name__)

POLL_SECONDS = 300
_BAD_STATUSES = frozenset({"degraded", "unhealthy"})


def _list_account_domains():
    res, status = mx_request_raw("GET", "/domains")
    if status != 200:
        logger.warning("DNS monitor: domain list failed with status %s", status)
        return []
    return [str(domain).lower() for domain in res.get("data", []) if domain]


def _domain_overall(domain):
    health = build_setup_health(domain)
    if not health:
        return None
    return health.get("overall")


def _run_domain_checks(domains):
    results = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_domain_overall, domain): domain for domain in domains}
        for future in as_completed(futures):
            domain = futures[future]
            try:
                results[domain] = future.result()
            except Exception as exc:
                logger.warning("DNS monitor check failed for %s: %s", domain, exc)
    return results


def maybe_run_dns_health_monitor():
    """Run a scheduled DNS scan when the monitor is enabled and the interval elapsed."""
    if not cf_is_configured():
        return

    config = get_notification_settings()
    monitor = config.get("dns_monitor") or {}
    if not monitor.get("enabled") or not config.get("enabled"):
        return

    interval_hours = max(1, int(monitor.get("interval_hours") or 24))
    state = get_dns_health_state()
    last_run = state.get("last_run_at")
    now = time.time()
    if last_run and (now - float(last_run)) < interval_hours * 3600:
        return

    domains = _list_account_domains()
    if not domains:
        save_dns_health_state({"last_run_at": now, "domains": {}})
        return

    previous = state.get("domains") or {}
    current = _run_domain_checks(domains)
    alerts = []
    recoveries = []
    for domain, overall in current.items():
        if not overall:
            continue
        prev = previous.get(domain)
        if overall in _BAD_STATUSES and prev not in _BAD_STATUSES:
            alerts.append({"domain": domain, "overall": overall, "previous": prev})
        elif overall == "healthy" and prev in _BAD_STATUSES:
            recoveries.append({"domain": domain, "previous": prev})

    if alerts:
        audit(
            "dns.health_alert",
            target=",".join(item["domain"] for item in alerts[:10]),
            details={"domains": alerts, "count": len(alerts)},
        )
    if recoveries:
        audit(
            "dns.health_recovered",
            target=",".join(item["domain"] for item in recoveries[:10]),
            details={"domains": recoveries, "count": len(recoveries)},
        )

    save_dns_health_state({"last_run_at": now, "domains": current})


def start_dns_health_monitor(app):
    """Background loop; checks every POLL_SECONDS whether a scan is due."""

    def loop():
        while True:
            time.sleep(POLL_SECONDS)
            try:
                with app.app_context():
                    maybe_run_dns_health_monitor()
            except Exception as exc:
                logger.exception("DNS health monitor tick failed: %s", exc)

    thread = threading.Thread(target=loop, daemon=True, name="dns-health-monitor")
    thread.start()
