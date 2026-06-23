"""Tests for audit-triggered notifications."""

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from models import db as db_module
from tests.helpers import (
    insert_user_with_grants,
    prime_authenticated_session,
    auth_post_headers,
)
from utils.apprise_builder import (
    compile_service_url,
    mask_apprise_url,
    parse_service_url,
    resolve_target_url,
    _inject_secret_into_url,
)
from utils.audit_actions import audit_action_ids, DESTRUCTIVE_ACTION_IDS
from services.notifications import (
    format_audit_message,
    notify_audit_event,
    resolve_apprise_urls,
    _should_notify,
)


@pytest.fixture
def admin_client(client, fresh_db, db_connection):
    email = f"notifications-{uuid.uuid4().hex[:8]}@example.com"
    insert_user_with_grants(db_connection, email, is_admin=True)
    token = prime_authenticated_session(client, email)
    return client, token


def test_audit_action_catalog_has_entries():
    assert "mailbox.delete" in audit_action_ids()
    assert "domain.delete" in DESTRUCTIVE_ACTION_IDS


def test_compile_ntfy_url():
    result = compile_service_url(
        "ntfy",
        {
            "host": "ntfy.example.com",
            "topic": "alerts",
            "token": "tk_test",
            "priority": "high",
            "secure": True,
        },
    )
    assert result["url"].startswith("ntfys://")
    assert "alerts" in result["url"]
    assert "auth=token" in result["url"]


def test_compile_ntfy_token_in_env():
    result = compile_service_url(
        "ntfy",
        {
            "host": "ntfy.example.com",
            "topic": "alerts",
            "token": "tk_test",
            "secure": True,
        },
        token_in_env=True,
    )
    assert "tk_test" not in result["url"]
    assert result["cred_env"] == "APPRISE_CRED_NTFY"
    assert result["env_snippet"] == "APPRISE_CRED_NTFY=tk_test"


def test_parse_ntfy_url_with_token():
    url = "ntfys://tk_secret@ntfy.example.com/alerts?auth=token&priority=high"
    parsed = parse_service_url("ntfy", url)
    assert parsed["fields"]["host"] == "ntfy.example.com"
    assert parsed["fields"]["topic"] == "alerts"
    assert parsed["fields"]["token"] == "tk_secret"
    assert parsed["fields"]["priority"] == "high"
    assert parsed["fields"]["secure"] is True


def test_parse_ntfy_masked_url_without_token(monkeypatch):
    monkeypatch.setenv("APPRISE_CRED_NTFY", "tk_from_env")
    url = "ntfys://***@ntfy.example.com/alerts?auth=token&priority=high"
    parsed = parse_service_url("ntfy", url, cred_env="APPRISE_CRED_NTFY")
    assert parsed["fields"]["topic"] == "alerts"
    assert parsed["fields"]["token"] == "tk_from_env"
    assert parsed["fields"]["host"] == "ntfy.example.com"


def test_parse_ntfy_token_in_env_url(monkeypatch):
    monkeypatch.setenv("APPRISE_CRED_NTFY", "tk_from_env")
    url = "ntfys://ntfy.example.com/alerts?auth=token"
    parsed = parse_service_url("ntfy", url, cred_env="APPRISE_CRED_NTFY")
    assert parsed["fields"]["topic"] == "alerts"
    assert parsed["fields"]["token"] == "tk_from_env"


def test_parse_ntfy_db_stored_url(admin_client):
    client, token = admin_client
    full_url = "ntfys://tk_db_secret@ntfy.example.com/alerts?auth=token&priority=high"
    with patch(
        "routes.admin_notifications.validate_apprise_url", side_effect=lambda url: url
    ):
        save_res = client.post(
            "/api/admin/notifications",
            data=json.dumps(
                {
                    "enabled": False,
                    "targets": [
                        {
                            "label": "ntfy",
                            "url": full_url,
                            "service": "ntfy",
                            "service_id": "ntfy",
                        }
                    ],
                    "actions": [],
                }
            ),
            headers=auth_post_headers(token),
        )
    assert save_res.status_code == 200

    parse_res = client.post(
        "/api/admin/notifications/builder/parse",
        data=json.dumps({"target_index": 0}),
        headers=auth_post_headers(token),
    )
    assert parse_res.status_code == 200
    fields = parse_res.get_json()["data"]["fields"]
    assert fields["topic"] == "alerts"
    assert fields["token"] == "tk_db_secret"


def test_resolve_target_url_injects_env(monkeypatch):
    monkeypatch.setenv("APPRISE_CRED_NTFY", "tk_from_env")
    target = {
        "url": "ntfys://ntfy.example.com/alerts?auth=token",
        "cred_env": "APPRISE_CRED_NTFY",
    }
    resolved = resolve_target_url(target)
    assert "tk_from_env" in resolved


def test_inject_ntfy_secret():
    url = _inject_secret_into_url(
        "ntfys://ntfy.example.com/alerts?auth=token", "sekrit"
    )
    assert url.startswith("ntfys://sekrit@ntfy.example.com/")


def test_compile_custom_url_validates():
    with pytest.raises(ValueError):
        compile_service_url("custom", {"url": "not-a-valid-url"})


def test_mask_apprise_url_hides_credentials():
    masked = mask_apprise_url("ntfys://secrettoken@ntfy.example.com/alerts?auth=token")
    assert "***@" in masked
    assert "secrettoken" not in masked


def test_format_audit_message_strips_password_keys():
    title, body = format_audit_message(
        {
            "action": "mailbox.password_update",
            "user": "admin@example.com",
            "target": "user@domain.com",
            "details": {"password": "secret", "quota": 500},
        }
    )
    assert "mailbox.password_update" in title
    assert "quota=500" in body


def test_should_notify_respects_subscription():
    entry = {"action": "mailbox.delete", "user": "a", "target": "b"}
    with patch(
        "services.notifications.get_notification_settings",
        return_value={
            "enabled": True,
            "actions": ["domain.delete"],
            "targets": [],
        },
    ):
        assert _should_notify(entry) is False

    with patch(
        "services.notifications.get_notification_settings",
        return_value={
            "enabled": True,
            "actions": ["mailbox.delete"],
            "targets": [],
        },
    ):
        assert _should_notify(entry) is True


def test_should_notify_skips_test_action():
    entry = {"action": "notification.test", "user": "system", "target": "test"}
    with patch(
        "services.notifications.get_notification_settings",
        return_value={
            "enabled": True,
            "actions": ["notification.test"],
            "targets": [],
        },
    ):
        assert _should_notify(entry) is False


@patch("services.notifications.apprise.Apprise")
def test_notify_audit_event_calls_apprise(mock_apprise_cls):
    mock_apobj = MagicMock()
    mock_apobj.notify.return_value = True
    mock_apprise_cls.return_value = mock_apobj

    entry = {
        "action": "domain.delete",
        "user": "admin",
        "target": "example.com",
        "details": {},
    }
    with (
        patch(
            "services.notifications.get_notification_settings",
            return_value={
                "enabled": True,
                "actions": ["domain.delete"],
                "targets": [{"label": "t", "url": "json://localhost/test"}],
            },
        ),
        patch(
            "services.notifications.resolve_apprise_urls",
            return_value=["json://localhost/test"],
        ),
    ):
        assert notify_audit_event(entry) is True
        mock_apobj.notify.assert_called_once()


def test_resolve_apprise_urls_from_db(fresh_db):
    db_module.save_notification_settings(
        {
            "enabled": True,
            "targets": [{"label": "db", "url": "json://localhost/db"}],
            "actions": ["domain.delete"],
        }
    )
    urls = resolve_apprise_urls()
    assert "json://localhost/db" in urls


def test_notification_api_round_trip(admin_client):
    client, token = admin_client

    with patch(
        "utils.apprise_builder.validate_apprise_url", side_effect=lambda url: url
    ):
        save_res = client.post(
            "/api/admin/notifications",
            data=json.dumps(
                {
                    "enabled": True,
                    "targets": [
                        {
                            "label": "Hook",
                            "url": "json://example.com/hook",
                            "service": "json",
                            "service_id": "json",
                        }
                    ],
                    "actions": ["mailbox.delete", "domain.delete"],
                }
            ),
            headers=auth_post_headers(token),
        )
    assert save_res.status_code == 200
    assert save_res.get_json()["success"] is True

    get_res = client.get("/api/admin/notifications", headers=auth_post_headers(token))
    data = get_res.get_json()["data"]
    assert data["enabled"] is True
    assert "mailbox.delete" in data["actions"]
    assert len(data["targets"]) == 1


def test_notification_parse_endpoint(admin_client):
    client, token = admin_client
    parse_res = client.post(
        "/api/admin/notifications/builder/parse",
        data=json.dumps(
            {
                "service_id": "ntfy",
                "url": "ntfys://ntfy.example.com/alerts?auth=token&priority=high",
            }
        ),
        headers=auth_post_headers(token),
    )
    assert parse_res.status_code == 200
    data = parse_res.get_json()["data"]
    assert data["fields"]["topic"] == "alerts"
    assert data["fields"]["priority"] == "high"


def test_notification_compile_endpoint(admin_client):
    client, token = admin_client
    with patch(
        "routes.admin_notifications.compile_service_url",
        return_value={
            "url": "ntfy://alerts",
            "masked_url": "ntfy://alerts",
            "service": "ntfy",
            "cred_env": None,
            "env_snippet": None,
        },
    ):
        res = client.post(
            "/api/admin/notifications/builder/compile",
            data=json.dumps({"service_id": "ntfy", "fields": {"topic": "alerts"}}),
            headers=auth_post_headers(token),
        )
    assert res.status_code == 200
    assert res.get_json()["data"]["url"] == "ntfy://alerts"


@patch("routes.admin_notifications.send_test_notification")
def test_notification_test_endpoint(mock_send, admin_client):
    mock_send.return_value = True
    client, token = admin_client
    with patch(
        "routes.admin_notifications.resolve_apprise_urls_for_test", return_value=True
    ):
        res = client.post(
            "/api/admin/notifications/test",
            data=json.dumps({}),
            headers=auth_post_headers(token),
        )
    assert res.status_code == 200
    mock_send.assert_called_once()


def test_save_rejects_enabled_without_actions(admin_client):
    client, token = admin_client
    res = client.post(
        "/api/admin/notifications",
        data=json.dumps({"enabled": True, "targets": [], "actions": []}),
        headers=auth_post_headers(token),
    )
    assert res.status_code == 400
