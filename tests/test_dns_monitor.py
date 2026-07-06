"""Tests for scheduled DNS health monitoring."""

import time
from unittest.mock import patch

from models import db
from services.dns_monitor import maybe_run_dns_health_monitor


def test_dns_monitor_skips_when_disabled(fresh_db):
    fresh_db.save_notification_settings(
        {
            "enabled": True,
            "targets": [{"label": "x", "url": "json://hooks.example.com", "service": "json"}],
            "actions": ["dns.health_alert"],
            "dns_monitor": {"enabled": False, "interval_hours": 1},
        }
    )
    with patch("services.dns_monitor._list_account_domains") as mock_list:
        maybe_run_dns_health_monitor()
    mock_list.assert_not_called()


def test_dns_monitor_alerts_on_new_unhealthy(fresh_db):
    fresh_db.save_notification_settings(
        {
            "enabled": True,
            "targets": [{"label": "x", "url": "json://hooks.example.com", "service": "json"}],
            "actions": ["dns.health_alert"],
            "dns_monitor": {"enabled": True, "interval_hours": 1},
        }
    )
    fresh_db.save_dns_health_state(
        {"last_run_at": None, "domains": {"example.com": "healthy"}}
    )
    with (
        patch(
            "services.dns_monitor._list_account_domains",
            return_value=["example.com"],
        ),
        patch(
            "services.dns_monitor._run_domain_checks",
            return_value={"example.com": "unhealthy"},
        ),
        patch("services.dns_monitor.audit") as mock_audit,
    ):
        maybe_run_dns_health_monitor()

    mock_audit.assert_called_once()
    assert mock_audit.call_args[0][0] == "dns.health_alert"


def test_dns_monitor_respects_interval(fresh_db):
    fresh_db.save_notification_settings(
        {
            "enabled": True,
            "targets": [{"label": "x", "url": "json://hooks.example.com", "service": "json"}],
            "actions": ["dns.health_alert"],
            "dns_monitor": {"enabled": True, "interval_hours": 24},
        }
    )
    fresh_db.save_dns_health_state(
        {"last_run_at": time.time(), "domains": {"example.com": "healthy"}}
    )
    with patch("services.dns_monitor._list_account_domains") as mock_list:
        maybe_run_dns_health_monitor()
    mock_list.assert_not_called()


def test_dns_monitor_runs_without_cloudflare(fresh_db):
    fresh_db.save_notification_settings(
        {
            "enabled": True,
            "targets": [{"label": "x", "url": "json://hooks.example.com", "service": "json"}],
            "actions": ["dns.health_alert"],
            "dns_monitor": {"enabled": True, "interval_hours": 1},
        }
    )
    fresh_db.save_dns_health_state({"last_run_at": None, "domains": {}})
    with (
        patch(
            "services.dns_monitor._list_account_domains",
            return_value=["example.com"],
        ) as mock_list,
        patch(
            "services.dns_monitor._run_domain_checks",
            return_value={"example.com": "healthy"},
        ),
    ):
        maybe_run_dns_health_monitor()
    mock_list.assert_called_once()


def test_dns_monitor_preserves_state_on_failed_check(fresh_db):
    fresh_db.save_notification_settings(
        {
            "enabled": True,
            "targets": [{"label": "x", "url": "json://hooks.example.com", "service": "json"}],
            "actions": ["dns.health_alert"],
            "dns_monitor": {"enabled": True, "interval_hours": 1},
        }
    )
    fresh_db.save_dns_health_state(
        {"last_run_at": None, "domains": {"example.com": "unhealthy"}}
    )
    with (
        patch(
            "services.dns_monitor._list_account_domains",
            return_value=["example.com"],
        ),
        patch(
            "services.dns_monitor._run_domain_checks",
            return_value={"example.com": None},
        ),
        patch("services.dns_monitor.audit") as mock_audit,
    ):
        maybe_run_dns_health_monitor()

    mock_audit.assert_not_called()
    saved = fresh_db.get_dns_health_state()
    assert saved["domains"]["example.com"] == "unhealthy"


def test_dns_monitor_skips_run_when_domain_list_fails(fresh_db):
    fresh_db.save_notification_settings(
        {
            "enabled": True,
            "targets": [{"label": "x", "url": "json://hooks.example.com", "service": "json"}],
            "actions": ["dns.health_alert"],
            "dns_monitor": {"enabled": True, "interval_hours": 1},
        }
    )
    previous_last_run = time.time() - 7200
    fresh_db.save_dns_health_state(
        {"last_run_at": previous_last_run, "domains": {"example.com": "healthy"}}
    )
    with (
        patch("services.dns_monitor._list_account_domains", return_value=None),
        patch("services.dns_monitor._run_domain_checks") as mock_checks,
    ):
        maybe_run_dns_health_monitor()

    mock_checks.assert_not_called()
    saved = fresh_db.get_dns_health_state()
    assert saved["last_run_at"] == previous_last_run
