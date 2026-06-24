"""Scheduled mailbox quota and send-limit checks with audit/notification hooks."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from models.db import (
    get_notification_settings,
    get_quota_monitor_state,
    save_quota_monitor_state,
)
from services.mxroute import audit, mx_request_raw

logger = logging.getLogger(__name__)

_RECOVER_MARGIN = 5


def _clamp_percent(raw, default=90):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(50, min(99, value))


def _clamp_interval_hours(raw):
    try:
        hours = int(raw)
    except (TypeError, ValueError):
        hours = 12
    return max(1, min(168, hours))


def _list_account_domains():
    res, status = mx_request_raw("GET", "/domains")
    if status != 200:
        logger.warning("Quota monitor: domain list failed with status %s", status)
        return []
    return [str(domain).lower() for domain in res.get("data", []) if domain]


def _fetch_domain_mailboxes(domain):
    res, status = mx_request_raw("GET", f"/domains/{domain}/email-accounts")
    if status != 200:
        logger.warning("Quota monitor: mailbox list failed for %s (%s)", domain, status)
        return []
    data = res.get("data")
    return data if isinstance(data, list) else []


def _mailbox_key(username, domain):
    return f"{str(username).strip().lower()}@{str(domain).strip().lower()}"


def _quota_percent(account):
    try:
        quota = int(account.get("quota") or 0)
    except (TypeError, ValueError):
        return None
    if quota <= 0:
        return None
    usage = float(account.get("usage") or 0)
    return (usage / quota) * 100


def _send_percent(account):
    try:
        limit = int(account.get("limit") or 0)
    except (TypeError, ValueError):
        return None
    if limit <= 0:
        return None
    sent = float(account.get("sent") or 0)
    return (sent / limit) * 100


def _collect_mailbox_usage(domains):
    results = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(_fetch_domain_mailboxes, domain): domain for domain in domains
        }
        for future in as_completed(futures):
            domain = futures[future]
            try:
                for account in future.result():
                    username = account.get("username")
                    if not username:
                        continue
                    key = _mailbox_key(username, domain)
                    results[key] = {
                        "mailbox": key,
                        "domain": domain,
                        "username": str(username).lower(),
                        "quota_percent": _quota_percent(account),
                        "send_percent": _send_percent(account),
                    }
            except Exception as exc:
                logger.warning("Quota monitor check failed for %s: %s", domain, exc)
    return results


def maybe_run_quota_monitor():
    """Run a scheduled mailbox usage scan when the monitor is enabled and due."""
    config = get_notification_settings()
    monitor = config.get("quota_monitor") or {}
    if not monitor.get("enabled") or not config.get("enabled"):
        return

    interval_hours = _clamp_interval_hours(monitor.get("interval_hours"))
    quota_threshold = _clamp_percent(monitor.get("quota_percent"), 90)
    send_threshold = _clamp_percent(monitor.get("send_percent"), 90)
    recover_quota = max(50, quota_threshold - _RECOVER_MARGIN)
    recover_send = max(50, send_threshold - _RECOVER_MARGIN)

    state = get_quota_monitor_state()
    last_run = state.get("last_run_at")
    now = time.time()
    if last_run and (now - float(last_run)) < interval_hours * 3600:
        return

    domains = _list_account_domains()
    if not domains:
        save_quota_monitor_state({"last_run_at": now, "mailboxes": {}})
        return

    previous = state.get("mailboxes") or {}
    current_checks = _collect_mailbox_usage(domains)
    current = {}
    quota_alerts = []
    quota_recoveries = []
    send_alerts = []
    send_recoveries = []

    for key, data in current_checks.items():
        prev = previous.get(key) or {}
        quota_percent = data.get("quota_percent")
        send_percent = data.get("send_percent")

        quota_alert = quota_percent is not None and quota_percent >= quota_threshold
        send_alert = send_percent is not None and send_percent >= send_threshold
        prev_quota_alert = bool(prev.get("quota_alert"))
        prev_send_alert = bool(prev.get("send_alert"))

        current[key] = {"quota_alert": quota_alert, "send_alert": send_alert}

        if quota_alert and not prev_quota_alert:
            quota_alerts.append({**data, "quota_percent": round(quota_percent, 1)})
        elif (
            not quota_alert
            and prev_quota_alert
            and quota_percent is not None
            and quota_percent < recover_quota
        ):
            quota_recoveries.append({**data, "quota_percent": round(quota_percent, 1)})

        if send_alert and not prev_send_alert:
            send_alerts.append({**data, "send_percent": round(send_percent, 1)})
        elif (
            not send_alert
            and prev_send_alert
            and send_percent is not None
            and send_percent < recover_send
        ):
            send_recoveries.append({**data, "send_percent": round(send_percent, 1)})

    if quota_alerts:
        audit(
            "mailbox.quota_alert",
            target=",".join(item["mailbox"] for item in quota_alerts[:10]),
            details={"mailboxes": quota_alerts, "count": len(quota_alerts)},
        )
    if quota_recoveries:
        audit(
            "mailbox.quota_recovered",
            target=",".join(item["mailbox"] for item in quota_recoveries[:10]),
            details={"mailboxes": quota_recoveries, "count": len(quota_recoveries)},
        )
    if send_alerts:
        audit(
            "mailbox.send_limit_alert",
            target=",".join(item["mailbox"] for item in send_alerts[:10]),
            details={"mailboxes": send_alerts, "count": len(send_alerts)},
        )
    if send_recoveries:
        audit(
            "mailbox.send_limit_recovered",
            target=",".join(item["mailbox"] for item in send_recoveries[:10]),
            details={"mailboxes": send_recoveries, "count": len(send_recoveries)},
        )

    save_quota_monitor_state({"last_run_at": now, "mailboxes": current})
