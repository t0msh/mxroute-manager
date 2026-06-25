"""HTTP tests for OIDC login redirect and callback."""

from unittest.mock import patch

import pytest

from tests.helpers import (
    OIDC_DISCOVERY,
    enable_oidc_settings,
    insert_user_with_grants,
    patch_oidc_http,
    prime_oidc_state,
)


@pytest.fixture(autouse=True)
def clear_oidc_test_tables(db_connection):
    db_connection.execute("DELETE FROM delegations")
    db_connection.execute("DELETE FROM users")
    db_connection.commit()


@pytest.fixture
def oidc_on(monkeypatch):
    enable_oidc_settings(monkeypatch)


def test_oidc_callback_disabled_redirects_home(client, monkeypatch):
    monkeypatch.setenv("OIDC_ENABLED", "false")
    from models import db as db_module

    db_module.invalidate_settings_cache()

    response = client.get("/oidc/callback?state=x&code=y", follow_redirects=False)
    assert response.status_code == 302
    assert response.location.endswith("/")


def test_oidc_callback_rejects_state_mismatch(oidc_on, client):
    prime_oidc_state(client, "expected-state")

    with patch("routes.auth.get_oidc_config", return_value=OIDC_DISCOVERY):
        response = client.get("/oidc/callback?state=wrong-state&code=auth-code")

    assert response.status_code == 400
    assert "csrf" in response.get_data(as_text=True).lower()


def test_oidc_callback_rejects_missing_code(oidc_on, client):
    state = prime_oidc_state(client)

    with patch("routes.auth.get_oidc_config", return_value=OIDC_DISCOVERY):
        response = client.get(f"/oidc/callback?state={state}")

    assert response.status_code == 400
    assert "authorization code" in response.get_data(as_text=True).lower()


def test_oidc_callback_rejects_unknown_user(oidc_on, client):
    state = prime_oidc_state(client)
    userinfo = {
        "email": "stranger@example.com",
        "email_verified": True,
        "groups": [],
    }

    with (
        patch("routes.auth.get_oidc_config", return_value=OIDC_DISCOVERY),
        patch_oidc_http(userinfo_data=userinfo),
        patch("routes.auth.write_audit_log"),
    ):
        response = client.get(f"/oidc/callback?state={state}&code=auth-code")

    assert response.status_code == 200
    assert b"do not have access" in response.data
    with client.session_transaction() as sess:
        assert "user" not in sess


def test_oidc_callback_logs_in_delegated_user(oidc_on, fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "delegate@example.com",
        grants=[{"domain": "example.com", "permissions": ["emails"]}],
        password=None,
    )
    state = prime_oidc_state(client)
    userinfo = {
        "email": "delegate@example.com",
        "email_verified": True,
        "groups": [],
    }

    with (
        patch("routes.auth.get_oidc_config", return_value=OIDC_DISCOVERY),
        patch_oidc_http(userinfo_data=userinfo),
        patch("routes.auth.write_audit_log"),
    ):
        response = client.get(
            f"/oidc/callback?state={state}&code=auth-code", follow_redirects=False
        )

    assert response.status_code == 302
    assert response.location.endswith("/")
    with client.session_transaction() as sess:
        user = sess.get("user")
        assert user["email"] == "delegate@example.com"
        assert user["is_admin"] is False
        assert user["domain_grants"]["example.com"] == ["emails"]


def test_oidc_callback_promotes_admin_by_configured_email(
    oidc_on, fresh_db, client, db_connection
):
    state = prime_oidc_state(client)
    userinfo = {
        "email": "oidc-admin@example.com",
        "email_verified": True,
        "groups": [],
    }

    with (
        patch("routes.auth.get_oidc_config", return_value=OIDC_DISCOVERY),
        patch_oidc_http(userinfo_data=userinfo),
        patch("routes.auth.write_audit_log"),
    ):
        response = client.get(
            f"/oidc/callback?state={state}&code=auth-code", follow_redirects=False
        )

    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess["user"]["is_admin"] is True
    assert (
        db_connection.execute(
            "SELECT is_admin FROM users WHERE email = ?",
            ("oidc-admin@example.com",),
        ).fetchone()[0]
        == 1
    )


def test_oidc_callback_promotes_admin_by_group(
    oidc_on, fresh_db, client, db_connection
):
    state = prime_oidc_state(client)
    userinfo = {
        "email": "group-admin@example.com",
        "email_verified": True,
        "groups": ["mxroute-admins", "users"],
    }

    with (
        patch("routes.auth.get_oidc_config", return_value=OIDC_DISCOVERY),
        patch_oidc_http(userinfo_data=userinfo),
        patch("routes.auth.write_audit_log"),
    ):
        response = client.get(
            f"/oidc/callback?state={state}&code=auth-code", follow_redirects=False
        )

    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess["user"]["email"] == "group-admin@example.com"
        assert sess["user"]["is_admin"] is True


def test_oidc_callback_rejects_unverified_email(oidc_on, fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "delegate@example.com",
        grants=[{"domain": "example.com", "permissions": ["emails"]}],
        password=None,
    )
    state = prime_oidc_state(client)
    userinfo = {
        "email": "delegate@example.com",
        "email_verified": False,
        "groups": [],
    }

    with (
        patch("routes.auth.get_oidc_config", return_value=OIDC_DISCOVERY),
        patch_oidc_http(userinfo_data=userinfo),
        patch("routes.auth.write_audit_log"),
    ):
        response = client.get(f"/oidc/callback?state={state}&code=auth-code")

    assert response.status_code == 403
    assert b"not verified" in response.data
    with client.session_transaction() as sess:
        assert "user" not in sess


def test_oidc_callback_accepts_string_email_verified(
    oidc_on, fresh_db, client, db_connection
):
    insert_user_with_grants(
        db_connection,
        "delegate@example.com",
        grants=[{"domain": "example.com", "permissions": ["emails"]}],
        password=None,
    )
    state = prime_oidc_state(client)
    userinfo = {
        "email": "delegate@example.com",
        "email_verified": "true",
        "groups": [],
    }

    with (
        patch("routes.auth.get_oidc_config", return_value=OIDC_DISCOVERY),
        patch_oidc_http(userinfo_data=userinfo),
        patch("routes.auth.write_audit_log"),
    ):
        response = client.get(
            f"/oidc/callback?state={state}&code=auth-code", follow_redirects=False
        )

    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess["user"]["email"] == "delegate@example.com"


def test_oidc_callback_allows_sub_when_email_claim_absent(
    oidc_on, fresh_db, client, db_connection
):
    insert_user_with_grants(
        db_connection,
        "opaque-subject@idp",
        grants=[{"domain": "example.com", "permissions": ["emails"]}],
        password=None,
    )
    state = prime_oidc_state(client)
    userinfo = {"sub": "opaque-subject@idp", "groups": []}

    with (
        patch("routes.auth.get_oidc_config", return_value=OIDC_DISCOVERY),
        patch_oidc_http(userinfo_data=userinfo),
        patch("routes.auth.write_audit_log"),
    ):
        response = client.get(
            f"/oidc/callback?state={state}&code=auth-code", follow_redirects=False
        )

    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess["user"]["email"] == "opaque-subject@idp"


def test_oidc_callback_missing_access_token(oidc_on, client):
    state = prime_oidc_state(client)

    with (
        patch("routes.auth.get_oidc_config", return_value=OIDC_DISCOVERY),
        patch_oidc_http(token_data={"token_type": "Bearer"}),
        patch("routes.auth.write_audit_log"),
    ):
        response = client.get(f"/oidc/callback?state={state}&code=auth-code")

    assert response.status_code == 500
    assert "access_token" in response.get_data(as_text=True)


def test_login_redirect_sends_user_to_provider(oidc_on, client):
    with patch("routes.auth.get_oidc_config", return_value=OIDC_DISCOVERY):
        response = client.get("/login/redirect", follow_redirects=False)

    assert response.status_code == 302
    assert response.location.startswith("https://idp.example/authorize")
    assert "client_id=test-client-id" in response.location
    with client.session_transaction() as sess:
        assert sess.get("oidc_state")
