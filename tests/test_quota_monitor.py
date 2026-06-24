"""Tests for scheduled mailbox quota/send-limit monitoring."""

from unittest.mock import patch

from services.quota_monitor import maybe_run_quota_monitor

DOMAIN = "example.com"


def test_quota_monitor_skips_when_disabled(fresh_db):
    fresh_db.save_notification_settings(
        {
            "enabled": True,
            "targets": [{"label": "t", "url": "json://localhost"}],
            "actions": ["mailbox.quota_alert"],
            "dns_monitor": {"enabled": False, "interval_hours": 24},
            "quota_monitor": {"enabled": False, "interval_hours": 1},
        }
    )
    with patch("services.quota_monitor._list_account_domains") as mock_list:
        maybe_run_quota_monitor()
    mock_list.assert_not_called()


def test_quota_monitor_alerts_on_quota_threshold(fresh_db):
    fresh_db.save_notification_settings(
        {
            "enabled": True,
            "targets": [{"label": "t", "url": "json://localhost"}],
            "actions": ["mailbox.quota_alert"],
            "dns_monitor": {"enabled": False, "interval_hours": 24},
            "quota_monitor": {
                "enabled": True,
                "interval_hours": 1,
                "quota_percent": 90,
                "send_percent": 90,
            },
        }
    )
    with (
        patch(
            "services.quota_monitor._list_account_domains",
            return_value=[DOMAIN],
        ),
        patch(
            "services.quota_monitor._fetch_domain_mailboxes",
            return_value=[
                {
                    "username": "alice",
                    "quota": 1000,
                    "usage": 950,
                    "limit": 1000,
                    "sent": 10,
                }
            ],
        ),
        patch("services.quota_monitor.audit") as mock_audit,
    ):
        maybe_run_quota_monitor()

    assert mock_audit.call_count == 1
    assert mock_audit.call_args[0][0] == "mailbox.quota_alert"


def test_quota_monitor_respects_interval(fresh_db):
    fresh_db.save_notification_settings(
        {
            "enabled": True,
            "targets": [{"label": "t", "url": "json://localhost"}],
            "actions": ["mailbox.quota_alert"],
            "dns_monitor": {"enabled": False, "interval_hours": 24},
            "quota_monitor": {"enabled": True, "interval_hours": 24},
        }
    )
    fresh_db.save_quota_monitor_state({"last_run_at": 9999999999, "mailboxes": {}})
    with patch("services.quota_monitor._list_account_domains") as mock_list:
        maybe_run_quota_monitor()
    mock_list.assert_not_called()
