"""HTTP tests for bulk DNS fix route."""

from unittest.mock import patch

import pytest

from tests.helpers import (
    auth_post_headers,
    insert_user_with_grants,
    prime_authenticated_session,
)

DOMAIN = "example.com"


@pytest.fixture(autouse=True)
def clear_users(db_connection):
    db_connection.execute("DELETE FROM delegations")
    db_connection.execute("DELETE FROM users")
    db_connection.commit()


@pytest.fixture
def admin_token(fresh_db, client, db_connection):
    insert_user_with_grants(db_connection, "admin@local", is_admin=True)
    return prime_authenticated_session(client, "admin@local")


def test_bulk_fix_requires_admin(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "editor@local",
        grants=[{"domain": DOMAIN, "permissions": ["dns"]}],
    )
    token = prime_authenticated_session(client, "editor@local")
    response = client.post(
        "/api/cloudflare/dns/fix-bulk",
        headers=auth_post_headers(token),
        json={"only_unhealthy": True},
    )
    assert response.status_code == 403


def test_bulk_fix_runs_for_admin(fresh_db, client, admin_token):
    payload = {
        "domains": [DOMAIN],
        "results": {DOMAIN: {"success": True, "fixed": ["mx"], "skipped": []}},
    }
    with patch("routes.cloudflare.fix_dns_bulk", return_value=payload) as mock_bulk:
        response = client.post(
            "/api/cloudflare/dns/fix-bulk",
            headers=auth_post_headers(admin_token),
            json={"domains": [DOMAIN]},
        )

    assert response.status_code == 200
    mock_bulk.assert_called_once_with([DOMAIN], None, only_unhealthy=False)
