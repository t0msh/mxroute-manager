"""Shared helpers for HTTP/integration tests."""

import json
import requests

from werkzeug.security import generate_password_hash


def csrf_token_from_response(client, path="/", host="reset.example.com"):
    response = client.get(path, headers={"Host": host})
    cookie_header = response.headers.get("Set-Cookie", "")
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith("csrf_token="):
            return part.split("=", 1)[1]
    return None


def insert_user_with_grants(
    conn, email, *, grants=None, is_admin=False, password="Abcd123!"
):
    """Insert a user and optional per-domain permission grants into the test DB."""
    grants = grants or []
    password_hash = generate_password_hash(password) if password else None
    conn.execute(
        "INSERT INTO users (email, password_hash, is_admin) VALUES (?, ?, ?)",
        (email.lower(), password_hash, 1 if is_admin else 0),
    )
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    if not is_admin:
        for grant in grants:
            conn.execute(
                "INSERT INTO delegations (user_id, domain, permissions) VALUES (?, ?, ?)",
                (user_id, grant["domain"].lower(), json.dumps(grant["permissions"])),
            )
    conn.commit()
    return user_id


def prime_authenticated_session(client, email):
    """Start a logged-in session for `email` (must exist in DB). Returns CSRF token."""
    from routes.auth import build_session_user

    token = csrf_token_from_response(client, path="/login", host="localhost")
    with client.session_transaction() as sess:
        sess["user"] = build_session_user(email)
    return token


def auth_post_headers(csrf_token):
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


def mx_json_response(payload, status=200):
    """Flask-compatible (response, status) tuple for mocking mx_request / audited_mx."""
    from flask import jsonify
    from app import app

    with app.app_context():
        return jsonify(payload), status


OIDC_DISCOVERY = {
    "authorization_endpoint": "https://idp.example/authorize",
    "token_endpoint": "https://idp.example/token",
    "userinfo_endpoint": "https://idp.example/userinfo",
}


def enable_oidc_settings(
    monkeypatch, *, admin_users="oidc-admin@example.com", admin_group="mxroute-admins"
):
    """Point OIDC config at test values and bust caches."""
    from models import db as db_module
    from utils.auth_helpers import clear_oidc_config_cache

    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "http://localhost:5000/oidc/callback")
    monkeypatch.setenv(
        "OIDC_DISCOVERY_URL", "https://idp.example/.well-known/openid-configuration"
    )
    monkeypatch.setenv("OIDC_ADMIN_USERS", admin_users)
    monkeypatch.setenv("OIDC_ADMIN_GROUP", admin_group)
    db_module.invalidate_settings_cache()
    clear_oidc_config_cache()


def prime_oidc_state(client, state="test-oidc-state"):
    with client.session_transaction() as sess:
        sess["oidc_state"] = state
    return state


class _MockHttpResponse:
    def __init__(self, json_data, *, ok=True):
        self._json_data = json_data
        self._ok = ok

    def raise_for_status(self):
        if not self._ok:
            raise requests.HTTPError("mock HTTP error")

    def json(self):
        return self._json_data


def patch_oidc_http(token_data=None, userinfo_data=None):
    """Return context managers patching token + userinfo HTTP calls in routes.auth."""
    from contextlib import contextmanager
    from unittest.mock import patch

    token_data = (
        token_data if token_data is not None else {"access_token": "access-token-123"}
    )
    userinfo_data = (
        userinfo_data
        if userinfo_data is not None
        else {"email": "delegate@example.com", "email_verified": True, "groups": []}
    )

    @contextmanager
    def _patch():
        with (
            patch(
                "routes.auth.requests.post", return_value=_MockHttpResponse(token_data)
            ) as mock_post,
            patch(
                "routes.auth.requests.get",
                return_value=_MockHttpResponse(userinfo_data),
            ) as mock_get,
        ):
            yield mock_post, mock_get

    return _patch()
