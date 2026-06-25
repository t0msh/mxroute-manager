"""HTTP tests for SpamAssassin settings, whitelist, and blacklist routes."""

from unittest.mock import patch

import pytest

from tests.helpers import (
    auth_post_headers,
    insert_user_with_grants,
    mx_json_response,
    prime_authenticated_session,
)

DOMAIN = "example.com"


@pytest.fixture(autouse=True)
def clear_spam_test_tables(db_connection):
    db_connection.execute("DELETE FROM delegations")
    db_connection.execute("DELETE FROM users")
    db_connection.commit()


@pytest.fixture
def spam_token(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "spamops@local",
        grants=[{"domain": DOMAIN, "permissions": ["spam"]}],
    )
    return prime_authenticated_session(client, "spamops@local")


def test_get_spam_settings_requires_login(client):
    response = client.get(f"/api/domains/{DOMAIN}/spam/settings")
    assert response.status_code == 401


def test_get_spam_settings_with_permission(fresh_db, client, spam_token):
    payload = {"success": True, "data": {"score": 5}}
    with patch("routes.spam.mx_domain_request", return_value=mx_json_response(payload)):
        response = client.get(f"/api/domains/{DOMAIN}/spam/settings")

    assert response.status_code == 200
    assert response.get_json()["data"]["score"] == 5


def test_get_spam_settings_forbidden_without_permission(
    fresh_db, client, db_connection
):
    insert_user_with_grants(
        db_connection,
        "emails-only@local",
        grants=[{"domain": DOMAIN, "permissions": ["emails"]}],
    )
    prime_authenticated_session(client, "emails-only@local")

    with patch("routes.spam.mx_domain_request") as mock_mx:
        response = client.get(f"/api/domains/{DOMAIN}/spam/settings")

    assert response.status_code == 403
    mock_mx.assert_not_called()


def test_update_spam_settings_requires_csrf(fresh_db, client, spam_token):
    with patch("routes.spam.audited_mx_domain") as mock_mx:
        response = client.patch(
            f"/api/domains/{DOMAIN}/spam/settings",
            json={"score": 7},
        )

    assert response.status_code == 400
    mock_mx.assert_not_called()


def test_update_spam_settings_calls_mxroute(fresh_db, client, spam_token):
    with patch(
        "routes.spam.audited_mx_domain",
        return_value=mx_json_response({"success": True}, 200),
    ) as mock_mx:
        response = client.patch(
            f"/api/domains/{DOMAIN}/spam/settings",
            headers=auth_post_headers(spam_token),
            json={"score": 7},
        )

    assert response.status_code == 200
    assert mock_mx.call_args[0][4] == "spam.settings_update"


def test_add_whitelist_entry_calls_mxroute(fresh_db, client, spam_token):
    body = {"entry": "trusted"}
    with patch(
        "routes.spam.audited_mx_domain",
        return_value=mx_json_response({"success": True}, 201),
    ) as mock_mx:
        response = client.post(
            f"/api/domains/{DOMAIN}/spam/whitelist",
            headers=auth_post_headers(spam_token),
            json=body,
        )

    assert response.status_code == 201
    assert mock_mx.call_args[0][4] == "spam.whitelist_add"
    assert mock_mx.call_args.kwargs["target"] == "trusted@example.com"


def test_delete_whitelist_entry_calls_mxroute(fresh_db, client, spam_token):
    with patch(
        "routes.spam.audited_mx_domain",
        return_value=mx_json_response({"success": True}, 200),
    ) as mock_mx:
        response = client.delete(
            f"/api/domains/{DOMAIN}/spam/whitelist/trusted",
            headers=auth_post_headers(spam_token),
        )

    assert response.status_code == 200
    assert mock_mx.call_args[0][4] == "spam.whitelist_remove"


def test_add_blacklist_entry_calls_mxroute(fresh_db, client, spam_token):
    with patch(
        "routes.spam.audited_mx_domain",
        return_value=mx_json_response({"success": True}, 201),
    ) as mock_mx:
        response = client.post(
            f"/api/domains/{DOMAIN}/spam/blacklist",
            headers=auth_post_headers(spam_token),
            json={"entry": "spammer"},
        )

    assert response.status_code == 201
    assert mock_mx.call_args[0][4] == "spam.blacklist_add"


def test_delete_blacklist_entry_calls_mxroute(fresh_db, client, spam_token):
    with patch(
        "routes.spam.audited_mx_domain",
        return_value=mx_json_response({"success": True}, 200),
    ) as mock_mx:
        response = client.delete(
            f"/api/domains/{DOMAIN}/spam/blacklist/spammer",
            headers=auth_post_headers(spam_token),
        )

    assert response.status_code == 200
    assert mock_mx.call_args[0][4] == "spam.blacklist_remove"
