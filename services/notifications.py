"""Audit-triggered notifications via Apprise."""

import logging
import os
import threading

import apprise

from app_meta import APP_NAME
from models.db import get_notification_settings
from utils.apprise_builder import mask_apprise_url, resolve_target_url, SERVICE_CRED_ENV

logger = logging.getLogger(__name__)

_SKIP_NOTIFY_ACTIONS = frozenset({"notification.test", "notification.send_failed"})


def _configured_cred_env_vars():
    return {key for key in SERVICE_CRED_ENV.values() if (os.getenv(key) or "").strip()}


def resolve_apprise_urls():
    """Collect deliverable Apprise URLs from DB targets (with env creds applied)."""
    config = get_notification_settings()
    urls = []
    seen = set()
    for target in config.get("targets") or []:
        url = resolve_target_url(target)
        if url and url not in seen:
            urls.append(url)
            seen.add(url)
    return urls


def is_notification_configured():
    config = get_notification_settings()
    if not config.get("enabled"):
        return False
    if not config.get("actions"):
        return False
    return bool(resolve_apprise_urls())


def _sanitize_details(details):
    if not isinstance(details, dict):
        return {}
    return {
        key: value
        for key, value in details.items()
        if "password" not in str(key).lower()
    }


def format_audit_message(entry):
    action = entry.get("action", "unknown")
    user = entry.get("user", "system")
    target = entry.get("target", "")
    details = _sanitize_details(entry.get("details"))

    title = f"[{APP_NAME}] {action}"
    lines = [f"{user} → {target}" if target else str(user)]
    if details:
        detail_parts = [f"{key}={value}" for key, value in details.items()]
        lines.append(", ".join(detail_parts))
    body = "\n".join(line for line in lines if line)
    return title, body


def _should_notify(entry):
    if not entry or entry.get("action") in _SKIP_NOTIFY_ACTIONS:
        return False
    config = get_notification_settings()
    if not config.get("enabled"):
        return False
    actions = config.get("actions") or []
    return entry.get("action") in actions


def _build_apprise():
    apobj = apprise.Apprise()
    for url in resolve_apprise_urls():
        apobj.add(url)
    return apobj


def notify_audit_event(entry):
    if not _should_notify(entry):
        return False
    title, body = format_audit_message(entry)
    apobj = _build_apprise()
    if not apobj:
        return False
    try:
        ok = apobj.notify(title=title, body=body)
        if not ok:
            logger.warning(
                "Apprise notify returned failure for action %s", entry.get("action")
            )
        return bool(ok)
    except Exception as exc:
        logger.warning(
            "Notification failed for action %s: %s", entry.get("action"), exc
        )
        return False


def send_test_notification():
    entry = {
        "action": "notification.test",
        "user": "system",
        "target": "test",
        "details": {"message": "This is a test notification from MXroute Manager."},
    }
    title, body = format_audit_message(entry)
    body = "Test notification — if you received this, delivery is working.\n\n" + body
    apobj = _build_apprise()
    if not apobj:
        raise RuntimeError("No notification targets configured")
    if not apobj.notify(title=title, body=body):
        raise RuntimeError("Apprise failed to send test notification")
    return True


def dispatch_audit_notification(entry):
    """Fire-and-forget notification dispatch from audit log writes."""
    # ponytail: daemon thread; failures logged only
    threading.Thread(target=notify_audit_event, args=(entry,), daemon=True).start()


def mask_notification_settings_for_response(config):
    configured_env = _configured_cred_env_vars()
    masked = {
        "enabled": bool(config.get("enabled")),
        "actions": list(config.get("actions") or []),
        "targets": [],
        "env_cred_keys": sorted(configured_env),
        "cred_env_map": SERVICE_CRED_ENV,
        "dns_monitor": {
            "enabled": bool((config.get("dns_monitor") or {}).get("enabled")),
            "interval_hours": int(
                (config.get("dns_monitor") or {}).get("interval_hours") or 24
            ),
        },
    }
    for target in config.get("targets") or []:
        url = str((target or {}).get("url") or "").strip()
        cred_env = str((target or {}).get("cred_env") or "").strip() or None
        masked["targets"].append(
            {
                "label": str((target or {}).get("label") or "").strip(),
                "url": mask_apprise_url(url),
                "service": (target or {}).get("service") or "",
                "service_id": (target or {}).get("service_id") or "",
                "cred_env": cred_env,
                "cred_env_configured": bool(cred_env and cred_env in configured_env),
            }
        )
    masked["target_count"] = len(masked["targets"])
    return masked
