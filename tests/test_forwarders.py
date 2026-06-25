"""HTTP tests for forwarders, catch-all, and domain pointers."""

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
def clear_forwarder_test_tables(db_connection):
    db_connection.execute("DELETE FROM delegations")
    db_connection.execute("DELETE FROM users")
    db_connection.commit()


@pytest.fixture
def forwarders_token(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "mailops@local",
        grants=[{"domain": DOMAIN, "permissions": ["forwarders"]}],
    )
    return prime_authenticated_session(client, "mailops@local")


def test_list_forwarders_requires_login(client):
    response = client.get(f"/api/domains/{DOMAIN}/forwarders")
    assert response.status_code == 401


def test_list_forwarders_allowed_with_permission(fresh_db, client, forwarders_token):
    payload = {
        "success": True,
        "data": [{"alias": "info", "forward_to": "me@example.com"}],
    }
    with patch("routes.emails.mx_domain_request", return_value=mx_json_response(payload)):
        response = client.get(f"/api/domains/{DOMAIN}/forwarders")

    assert response.status_code == 200
    assert response.get_json()["data"][0]["alias"] == "info"


def test_list_forwarders_forbidden_without_permission(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "emails-only@local",
        grants=[{"domain": DOMAIN, "permissions": ["emails"]}],
    )
    prime_authenticated_session(client, "emails-only@local")

    with patch("routes.emails.mx_domain_request") as mock_mx:
        response = client.get(f"/api/domains/{DOMAIN}/forwarders")

    assert response.status_code == 403
    mock_mx.assert_not_called()


def test_create_forwarder_requires_csrf(fresh_db, client, forwarders_token):
    with patch("routes.emails.audited_mx_domain") as mock_mx:
        response = client.post(
            f"/api/domains/{DOMAIN}/forwarders",
            json={"alias": "info", "forward_to": "me@example.com"},
        )

    assert response.status_code == 400
    assert "csrf" in response.get_json()["error"]["message"].lower()
    mock_mx.assert_not_called()


def test_create_forwarder_calls_mxroute(fresh_db, client, forwarders_token):
    body = {"alias": "info", "forward_to": "me@example.com"}
    with patch(
        "routes.emails.audited_mx_domain",
        return_value=mx_json_response({"success": True}, 201),
    ) as mock_mx:
        response = client.post(
            f"/api/domains/{DOMAIN}/forwarders",
            headers=auth_post_headers(forwarders_token),
            json=body,
        )

    assert response.status_code == 201
    mock_mx.assert_called_once()
    assert mock_mx.call_args[0][0] == "POST"
    assert mock_mx.call_args[0][4] == "forwarder.create"
    assert mock_mx.call_args.kwargs["target"] == "info@example.com"


def test_delete_forwarder_calls_mxroute(fresh_db, client, forwarders_token):
    with patch(
        "routes.emails.audited_mx_domain",
        return_value=mx_json_response({"success": True}, 200),
    ) as mock_mx:
        response = client.delete(
            f"/api/domains/{DOMAIN}/forwarders/info",
            headers=auth_post_headers(forwarders_token),
        )

    assert response.status_code == 200
    mock_mx.assert_called_once()
    assert mock_mx.call_args[0][0] == "DELETE"
    assert mock_mx.call_args[0][4] == "forwarder.delete"


def test_get_catch_all_with_permission(fresh_db, client, forwarders_token):
    payload = {
        "success": True,
        "data": {"enabled": True, "forward_to": "catch@example.com"},
    }
    with patch("routes.emails.mx_domain_request", return_value=mx_json_response(payload)):
        response = client.get(f"/api/domains/{DOMAIN}/catch-all")

    assert response.status_code == 200
    assert response.get_json()["data"]["enabled"] is True


def test_update_catch_all_requires_csrf(fresh_db, client, forwarders_token):
    with patch("routes.emails.audited_mx_domain") as mock_mx:
        response = client.patch(
            f"/api/domains/{DOMAIN}/catch-all",
            json={"enabled": True, "forward_to": "catch@example.com"},
        )

    assert response.status_code == 400
    mock_mx.assert_not_called()


def test_update_catch_all_calls_mxroute(fresh_db, client, forwarders_token):
    body = {"enabled": True, "forward_to": "catch@example.com"}
    with patch(
        "routes.emails.audited_mx_domain",
        return_value=mx_json_response({"success": True}, 200),
    ) as mock_mx:
        response = client.patch(
            f"/api/domains/{DOMAIN}/catch-all",
            headers=auth_post_headers(forwarders_token),
            json=body,
        )

    assert response.status_code == 200
    assert mock_mx.call_args[0][4] == "catchall.update"


def test_list_pointers_allowed_with_forwarders(fresh_db, client, forwarders_token):
    payload = {"success": True, "data": ["other.com"]}
    with patch("routes.domains.mx_domain_request", return_value=mx_json_response(payload)):
        response = client.get(f"/api/domains/{DOMAIN}/pointers")

    assert response.status_code == 200
    assert response.get_json()["data"] == ["other.com"]


def test_create_pointer_forbidden_without_forwarders_permission(
    fresh_db, client, db_connection
):
    insert_user_with_grants(
        db_connection,
        "dashboard-only@local",
        grants=[{"domain": DOMAIN, "permissions": ["dashboard"]}],
    )
    token = prime_authenticated_session(client, "dashboard-only@local")

    with patch("routes.domains.audited_mx_domain") as mock_mx:
        response = client.post(
            f"/api/domains/{DOMAIN}/pointers",
            headers=auth_post_headers(token),
            json={"pointer": "other.com"},
        )

    assert response.status_code == 403
    mock_mx.assert_not_called()
