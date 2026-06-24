"""Tests for scheduled DNS health monitoring."""

import time
from unittest.mock import patch

from models import db
from services.dns_monitor import maybe_run_dns_health_monitor


def test_dns_monitor_skips_when_disabled(fresh_db):
    fresh_db.save_notification_settings(
        {
            "enabled": True,
            "targets": [{"label": "x", "url": "json://localhost", "service": "json"}],
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
            "targets": [{"label": "x", "url": "json://localhost", "service": "json"}],
            "actions": ["dns.health_alert"],
            "dns_monitor": {"enabled": True, "interval_hours": 1},
        }
    )
    fresh_db.save_dns_health_state(
        {"last_run_at": None, "domains": {"example.com": "healthy"}}
    )
    with (
        patch("services.dns_monitor.cf_is_configured", return_value=True),
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
            "targets": [{"label": "x", "url": "json://localhost", "service": "json"}],
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
