"""Tests for branded reset portal email sender provisioning."""

from unittest.mock import patch

import pytest

from services.reset_portal_mail import (
    RESET_SENDER_ALIAS,
    build_portal_reset_from_address,
    ensure_reset_sender_forwarder,
)


def test_build_portal_reset_from_address_uses_portal_title():
    portal = {"portal_title": "Acme Corp"}
    assert (
        build_portal_reset_from_address(portal, "Example.COM")
        == "Acme Corp <reset@example.com>"
    )


def test_build_portal_reset_from_address_default_display_name():
    portal = {"portal_title": ""}
    assert (
        build_portal_reset_from_address(portal, "example.com")
        == "Password Reset <reset@example.com>"
    )


def test_ensure_reset_sender_forwarder_requires_admin_email():
    with pytest.raises(ValueError, match="contact email is required"):
        ensure_reset_sender_forwarder("example.com", admin_email="")


def test_ensure_reset_sender_forwarder_skips_when_catch_all_address():
    steps = []
    with patch(
        "services.reset_portal_mail.mx_request_raw",
        side_effect=[
            (
                {
                    "success": True,
                    "data": {"type": "address", "address": "catch@example.com"},
                },
                200,
            ),
        ],
    ) as mock_mx:
        outcome = ensure_reset_sender_forwarder("example.com", "admin@ops.com", steps)

    assert outcome == "skipped"
    assert mock_mx.call_count == 1
    assert any("Catch-all already configured" in step for step in steps)


def test_ensure_reset_sender_forwarder_skips_existing_forwarder():
    steps = []
    with patch(
        "services.reset_portal_mail.mx_request_raw",
        side_effect=[
            ({"success": True, "data": {"type": "fail"}}, 200),
            (
                {
                    "success": True,
                    "data": [
                        {
                            "alias": RESET_SENDER_ALIAS,
                            "destinations": ["admin@ops.com"],
                        },
                    ],
                },
                200,
            ),
        ],
    ) as mock_mx:
        outcome = ensure_reset_sender_forwarder("example.com", "admin@ops.com", steps)

    assert outcome == "skipped"
    assert mock_mx.call_count == 2
    assert any("already forwards" in step for step in steps)


def test_ensure_reset_sender_forwarder_creates_forwarder():
    steps = []
    with patch(
        "services.reset_portal_mail.mx_request_raw",
        side_effect=[
            ({"success": True, "data": {"type": "fail"}}, 200),
            ({"success": True, "data": []}, 200),
            ({"success": True}, 201),
        ],
    ) as mock_mx:
        outcome = ensure_reset_sender_forwarder("example.com", "admin@ops.com", steps)

    assert outcome == "added"
    assert mock_mx.call_args_list[-1][0] == (
        "POST",
        "/domains/example.com/forwarders",
        {"alias": RESET_SENDER_ALIAS, "destinations": ["admin@ops.com"]},
    )
    assert any("(added)" in step for step in steps)


def test_ensure_reset_sender_forwarder_updates_wrong_destination():
    steps = []
    with patch(
        "services.reset_portal_mail.mx_request_raw",
        side_effect=[
            ({"success": True, "data": {"type": "fail"}}, 200),
            (
                {
                    "success": True,
                    "data": [
                        {
                            "alias": RESET_SENDER_ALIAS,
                            "destinations": ["old@example.com"],
                        },
                    ],
                },
                200,
            ),
            ({"success": True}, 200),
            ({"success": True}, 201),
        ],
    ) as mock_mx:
        outcome = ensure_reset_sender_forwarder("example.com", "admin@ops.com", steps)

    assert outcome == "updated"
    assert mock_mx.call_args_list[-2][0][0] == "DELETE"
    assert mock_mx.call_args_list[-1][0][0] == "POST"
    assert any("(updated)" in step for step in steps)
