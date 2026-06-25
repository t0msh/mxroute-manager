"""HTTP tests for domain list and admin domain management routes."""

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
def clear_domain_tables(db_connection):
    db_connection.execute("DELETE FROM delegations")
    db_connection.execute("DELETE FROM users")
    db_connection.commit()


@pytest.fixture
def admin_token(fresh_db, client, db_connection):
    insert_user_with_grants(db_connection, "admin@local", is_admin=True)
    return prime_authenticated_session(client, "admin@local")


@pytest.fixture
def dashboard_token(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "viewer@local",
        grants=[{"domain": DOMAIN, "permissions": ["dashboard"]}],
    )
    return prime_authenticated_session(client, "viewer@local")


def test_create_domain_requires_admin(fresh_db, client, dashboard_token):
    with patch("routes.domains.audited_mx") as mock_mx:
        response = client.post(
            "/api/domains",
            headers=auth_post_headers(dashboard_token),
            json={"domain": "new.com"},
        )

    assert response.status_code == 403
    mock_mx.assert_not_called()


def test_create_domain_validates_name(fresh_db, client, admin_token):
    with patch("routes.domains.audited_mx") as mock_mx:
        response = client.post(
            "/api/domains",
            headers=auth_post_headers(admin_token),
            json={"domain": "bad domain"},
        )

    assert response.status_code == 400
    mock_mx.assert_not_called()


def test_create_domain_calls_mxroute(fresh_db, client, admin_token):
    with patch(
        "routes.domains.audited_mx",
        return_value=mx_json_response({"success": True}, 201),
    ) as mock_mx:
        response = client.post(
            "/api/domains",
            headers=auth_post_headers(admin_token),
            json={"domain": "new.com"},
        )

    assert response.status_code == 201
    mock_mx.assert_called_once()
    assert mock_mx.call_args.kwargs["target"] == "new.com"


def test_delete_domain_requires_admin(fresh_db, client, dashboard_token):
    with patch("routes.domains.audited_mx_domain") as mock_mx:
        response = client.delete(
            f"/api/domains/{DOMAIN}",
            headers=auth_post_headers(dashboard_token),
        )

    assert response.status_code == 403
    mock_mx.assert_not_called()


def test_delete_domain_calls_mxroute(fresh_db, client, admin_token):
    with patch(
        "routes.domains.audited_mx_domain",
        return_value=mx_json_response({"success": True}, 200),
    ) as mock_mx:
        response = client.delete(
            f"/api/domains/{DOMAIN}",
            headers=auth_post_headers(admin_token),
        )

    assert response.status_code == 200
    assert mock_mx.call_args[0][0] == "DELETE"
    assert mock_mx.call_args[0][1] == DOMAIN


def test_get_domain_details_allowed_with_dashboard(fresh_db, client, dashboard_token):
    with patch(
        "routes.domains.mx_domain_request",
        return_value=mx_json_response({"success": True, "data": {"domain": DOMAIN}}),
    ):
        response = client.get(f"/api/domains/{DOMAIN}")

    assert response.status_code == 200
    assert response.get_json()["data"]["domain"] == DOMAIN


def test_verification_key_admin_only(fresh_db, client, dashboard_token):
    with patch("routes.domains.mx_request") as mock_mx:
        response = client.get("/api/verification-key")

    assert response.status_code == 403
    mock_mx.assert_not_called()


def test_mail_status_toggle_admin_only(fresh_db, client, dashboard_token):
    with patch("routes.domains.audited_mx_domain") as mock_mx:
        response = client.patch(
            f"/api/domains/{DOMAIN}/mail-status",
            headers=auth_post_headers(dashboard_token),
            json={"mail_hosting": False},
        )

    assert response.status_code == 403
    mock_mx.assert_not_called()


def test_fleet_overview_returns_cached_domains(fresh_db, client, admin_token):
    import time

    fresh_db.save_fleet_overview_state(
        {
            "last_run_at": time.time(),
            "domains": {
                "alpha.com": {
                    "mail_hosting": True,
                    "dns": {"overall": "healthy", "checks": {"mx": {"status": "pass"}}},
                    "mailbox_count": 2,
                },
                "beta.com": {
                    "mail_hosting": False,
                    "dns": {"overall": "degraded", "checks": {}},
                    "mailbox_count": 0,
                },
            },
        }
    )
    with patch(
        "routes.domains.mx_request_raw",
        return_value=({"data": ["alpha.com", "beta.com"]}, 200),
    ):
        response = client.get("/api/fleet/overview")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert len(payload["data"]["domains"]) == 2
    assert payload["data"]["domains"][0]["domain"] == "alpha.com"


def test_fleet_overview_hides_mailbox_count_without_permission(
    fresh_db, client, db_connection
):
    import time

    insert_user_with_grants(
        db_connection,
        "dns@local",
        grants=[
            {"domain": "alpha.com", "permissions": ["dns"]},
            {"domain": "beta.com", "permissions": ["dns"]},
        ],
    )
    prime_authenticated_session(client, "dns@local")
    fresh_db.save_fleet_overview_state(
        {
            "last_run_at": time.time(),
            "domains": {
                "alpha.com": {
                    "mail_hosting": True,
                    "dns": {"overall": "healthy", "checks": {}},
                    "mailbox_count": 9,
                },
                "beta.com": {
                    "mail_hosting": True,
                    "dns": {"overall": "healthy", "checks": {}},
                    "mailbox_count": 1,
                },
            },
        }
    )
    response = client.get("/api/fleet/overview")

    assert response.status_code == 200
    rows = {row["domain"]: row for row in response.get_json()["data"]["domains"]}
    assert "mailbox_count" not in rows["alpha.com"]
    assert "mailbox_count" not in rows["beta.com"]

