"""Notification settings and background monitor state persistence."""

import json
import logging

from models.db_conn import get_conn
from models.db_constants import (
    DNS_HEALTH_STATE_KEY,
    FLEET_OVERVIEW_STATE_KEY,
    NOTIFICATION_SETTINGS_KEY,
    QUOTA_MONITOR_STATE_KEY,
)
from models.db_settings import get_config_value, invalidate_settings_cache

logger = logging.getLogger(__name__)


def _default_notification_settings():
    return {
        "enabled": False,
        "targets": [],
        "actions": [],
        "dns_monitor": _default_dns_monitor(),
        "quota_monitor": _default_quota_monitor(),
    }


def _default_dns_monitor():
    return {"enabled": False, "interval_hours": 24}


def _default_quota_monitor():
    return {
        "enabled": False,
        "interval_hours": 12,
        "quota_percent": 90,
        "send_percent": 90,
    }


def _clamp_monitor_interval(raw, default=24):
    try:
        hours = int(raw)
    except (TypeError, ValueError):
        hours = default
    return max(1, min(168, hours))


def _clamp_threshold_percent(raw, default=90):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(50, min(99, value))


def _clamp_dns_monitor_interval(raw):
    return _clamp_monitor_interval(raw, 24)


def get_notification_settings():
    raw = get_config_value(NOTIFICATION_SETTINGS_KEY, "")
    if not raw:
        return _default_notification_settings()
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        logger.warning("Invalid notification settings JSON; using defaults")
        return _default_notification_settings()
    if not isinstance(data, dict):
        return _default_notification_settings()
    monitor_raw = (
        data.get("dns_monitor") if isinstance(data.get("dns_monitor"), dict) else {}
    )
    quota_raw = (
        data.get("quota_monitor") if isinstance(data.get("quota_monitor"), dict) else {}
    )
    return {
        "enabled": bool(data.get("enabled")),
        "targets": data.get("targets") if isinstance(data.get("targets"), list) else [],
        "actions": data.get("actions") if isinstance(data.get("actions"), list) else [],
        "dns_monitor": {
            "enabled": bool(monitor_raw.get("enabled")),
            "interval_hours": _clamp_dns_monitor_interval(
                monitor_raw.get("interval_hours")
            ),
        },
        "quota_monitor": {
            "enabled": bool(quota_raw.get("enabled")),
            "interval_hours": _clamp_monitor_interval(
                quota_raw.get("interval_hours"), 12
            ),
            "quota_percent": _clamp_threshold_percent(
                quota_raw.get("quota_percent"), 90
            ),
            "send_percent": _clamp_threshold_percent(quota_raw.get("send_percent"), 90),
        },
    }


def get_dns_health_state():
    raw = get_config_value(DNS_HEALTH_STATE_KEY, "")
    if not raw:
        return {"last_run_at": None, "domains": {}}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {"last_run_at": None, "domains": {}}
    if not isinstance(data, dict):
        return {"last_run_at": None, "domains": {}}
    domains = data.get("domains")
    return {
        "last_run_at": data.get("last_run_at"),
        "domains": domains if isinstance(domains, dict) else {},
    }


def save_dns_health_state(state):
    if not isinstance(state, dict):
        raise ValueError("DNS health state must be an object")
    domains = state.get("domains")
    normalized = {
        "last_run_at": state.get("last_run_at"),
        "domains": domains if isinstance(domains, dict) else {},
    }
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (DNS_HEALTH_STATE_KEY, json.dumps(normalized, ensure_ascii=False)),
        )
        conn.commit()
    invalidate_settings_cache()
    return normalized


def get_fleet_overview_state():
    raw = get_config_value(FLEET_OVERVIEW_STATE_KEY, "")
    if not raw:
        return {"last_run_at": None, "domains": {}}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {"last_run_at": None, "domains": {}}
    if not isinstance(data, dict):
        return {"last_run_at": None, "domains": {}}
    domains = data.get("domains")
    return {
        "last_run_at": data.get("last_run_at"),
        "domains": domains if isinstance(domains, dict) else {},
    }


def save_fleet_overview_state(state):
    if not isinstance(state, dict):
        raise ValueError("Fleet overview state must be an object")
    domains = state.get("domains")
    normalized = {
        "last_run_at": state.get("last_run_at"),
        "domains": domains if isinstance(domains, dict) else {},
    }
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (FLEET_OVERVIEW_STATE_KEY, json.dumps(normalized, ensure_ascii=False)),
        )
        conn.commit()
    invalidate_settings_cache()
    return normalized


def get_quota_monitor_state():
    raw = get_config_value(QUOTA_MONITOR_STATE_KEY, "")
    if not raw:
        return {"last_run_at": None, "mailboxes": {}}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {"last_run_at": None, "mailboxes": {}}
    if not isinstance(data, dict):
        return {"last_run_at": None, "mailboxes": {}}
    mailboxes = data.get("mailboxes")
    return {
        "last_run_at": data.get("last_run_at"),
        "mailboxes": mailboxes if isinstance(mailboxes, dict) else {},
    }


def save_quota_monitor_state(state):
    if not isinstance(state, dict):
        raise ValueError("Quota monitor state must be an object")
    mailboxes = state.get("mailboxes")
    normalized = {
        "last_run_at": state.get("last_run_at"),
        "mailboxes": mailboxes if isinstance(mailboxes, dict) else {},
    }
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (QUOTA_MONITOR_STATE_KEY, json.dumps(normalized, ensure_ascii=False)),
        )
        conn.commit()
    invalidate_settings_cache()
    return normalized


def save_notification_settings(config):
    if not isinstance(config, dict):
        raise ValueError("Notification settings must be an object")
    monitor_raw = (
        config.get("dns_monitor") if isinstance(config.get("dns_monitor"), dict) else {}
    )
    quota_raw = (
        config.get("quota_monitor")
        if isinstance(config.get("quota_monitor"), dict)
        else {}
    )
    normalized = {
        "enabled": bool(config.get("enabled")),
        "targets": config.get("targets")
        if isinstance(config.get("targets"), list)
        else [],
        "actions": config.get("actions")
        if isinstance(config.get("actions"), list)
        else [],
        "dns_monitor": {
            "enabled": bool(monitor_raw.get("enabled")),
            "interval_hours": _clamp_dns_monitor_interval(
                monitor_raw.get("interval_hours")
            ),
        },
        "quota_monitor": {
            "enabled": bool(quota_raw.get("enabled")),
            "interval_hours": _clamp_monitor_interval(
                quota_raw.get("interval_hours"), 12
            ),
            "quota_percent": _clamp_threshold_percent(
                quota_raw.get("quota_percent"), 90
            ),
            "send_percent": _clamp_threshold_percent(quota_raw.get("send_percent"), 90),
        },
    }
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (NOTIFICATION_SETTINGS_KEY, json.dumps(normalized, ensure_ascii=False)),
        )
        conn.commit()
    invalidate_settings_cache()
    return normalized
