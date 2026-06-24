"""Scheduled fleet overview snapshots for the dashboard."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from models.db import get_fleet_overview_state, save_fleet_overview_state
from services.cloudflare_health import build_setup_health
from services.dns_health import apply_mail_hosting_context
from services.mxroute import mx_request_raw
from utils.validators import nested_dict_get

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 900


def _list_account_domains():
    res, status = mx_request_raw("GET", "/domains")
    if status != 200:
        logger.warning("Fleet overview: domain list failed with status %s", status)
        return []
    return [str(domain).lower() for domain in res.get("data", []) if domain]


def _slim_dns_for_cache(health):
    if not health:
        return None
    checks = health.get("checks") or {}
    slim_checks = {}
    for key, check in checks.items():
        if isinstance(check, dict) and check.get("status") is not None:
            slim_checks[key] = {"status": check["status"]}
    return {
        "overall": health.get("overall"),
        "checks": slim_checks,
        "cf_configured": health.get("cf_configured"),
    }


def _fleet_row_for_domain(domain):
    row = {"checked_at": time.time()}

    res, status = mx_request_raw("GET", f"/domains/{domain}")
    if status == 200:
        row["mail_hosting"] = bool(
            nested_dict_get(res, "data", "mail_hosting", default=True)
        )
    else:
        row["mail_hosting"] = None

    health = build_setup_health(domain)
    if health:
        if row.get("mail_hosting") is not None:
            health = apply_mail_hosting_context(health, row["mail_hosting"])
        row["dns"] = _slim_dns_for_cache(health)
    else:
        row["dns"] = None

    mb_res, mb_status = mx_request_raw("GET", f"/domains/{domain}/email-accounts")
    if mb_status == 200:
        data = mb_res.get("data")
        row["mailbox_count"] = len(data) if isinstance(data, list) else 0
    else:
        row["mailbox_count"] = None

    return row


def _run_domain_scans(domains):
    results = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(_fleet_row_for_domain, domain): domain for domain in domains
        }
        for future in as_completed(futures):
            domain = futures[future]
            try:
                results[domain] = future.result()
            except Exception as exc:
                logger.warning("Fleet overview scan failed for %s: %s", domain, exc)
    return results


def run_fleet_overview_scan():
    """Scan all account domains and persist a fleet overview snapshot."""
    domains = _list_account_domains()
    now = time.time()
    if not domains:
        return save_fleet_overview_state({"last_run_at": now, "domains": {}})

    current = _run_domain_scans(domains)
    return save_fleet_overview_state({"last_run_at": now, "domains": current})


def maybe_run_fleet_overview(*, force=False):
    """Run a fleet scan when forced or the refresh interval has elapsed."""
    if not force:
        state = get_fleet_overview_state()
        last_run = state.get("last_run_at")
        now = time.time()
        if last_run and (now - float(last_run)) < INTERVAL_SECONDS:
            return state
    return run_fleet_overview_scan()
