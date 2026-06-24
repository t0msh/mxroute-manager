"""Tests for scheduled fleet overview snapshots."""

import time
from unittest.mock import patch

from models import db
from services.fleet_monitor import maybe_run_fleet_overview, run_fleet_overview_scan


def test_fleet_overview_scan_persists_domain_rows(fresh_db):
    with (
        patch(
            "services.fleet_monitor._list_account_domains",
            return_value=["example.com"],
        ),
        patch(
            "services.fleet_monitor._fleet_row_for_domain",
            return_value={
                "mail_hosting": True,
                "dns": {"overall": "healthy", "checks": {"mx": {"status": "pass"}}},
                "mailbox_count": 2,
                "checked_at": time.time(),
            },
        ),
    ):
        state = run_fleet_overview_scan()

    assert state["domains"]["example.com"]["mailbox_count"] == 2
    assert state["last_run_at"] is not None


def test_fleet_overview_respects_interval(fresh_db):
    fresh_db.save_fleet_overview_state(
        {"last_run_at": time.time(), "domains": {"example.com": {"mailbox_count": 1}}}
    )
    with patch("services.fleet_monitor._list_account_domains") as mock_list:
        maybe_run_fleet_overview()
    mock_list.assert_not_called()


def test_fleet_overview_force_bypasses_interval(fresh_db):
    fresh_db.save_fleet_overview_state(
        {"last_run_at": time.time(), "domains": {"example.com": {"mailbox_count": 1}}}
    )
    with (
        patch(
            "services.fleet_monitor._list_account_domains",
            return_value=["example.com"],
        ),
        patch(
            "services.fleet_monitor._run_domain_scans",
            return_value={"example.com": {"mailbox_count": 3}},
        ),
    ):
        state = maybe_run_fleet_overview(force=True)

    assert state["domains"]["example.com"]["mailbox_count"] == 3
