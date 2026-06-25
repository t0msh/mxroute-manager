import secrets
from urllib.parse import urlencode

import requests
from flask import request, session, redirect, url_for, render_template, current_app

from models.db import (
    get_conn,
    get_oidc_admin_group,
    get_oidc_admin_users,
    get_oidc_client_id,
    get_oidc_client_secret,
    get_oidc_redirect_uri,
    get_oidc_scopes,
    is_oidc_enabled,
)
from routes.auth_blueprint import auth_bp
from routes.auth_session import build_session_user, start_user_session
from utils.auth_helpers import get_oidc_config
from utils.audit_log import write_audit_log


@auth_bp.route("/login/redirect")
def login_redirect():
    if not is_oidc_enabled():
        return redirect(url_for("home"))
    try:
        config = get_oidc_config()
    except Exception as e:
        current_app.logger.error(f"OIDC provider configuration failed: {e}")
        return render_template(
            "login.html",
            error="Single sign-on is temporarily unavailable. Please try again later.",
        ), 500

    auth_endpoint = config.get("authorization_endpoint")
    if not auth_endpoint:
        return (
            "Error: OIDC provider configuration does not define authorization_endpoint",
            500,
        )

    state = secrets.token_urlsafe(16)
    session["oidc_state"] = state

    params = {
        "client_id": get_oidc_client_id(),
        "response_type": "code",
        "scope": get_oidc_scopes(),
        "redirect_uri": get_oidc_redirect_uri(),
        "state": state,
    }

    auth_url = f"{auth_endpoint}?{urlencode(params)}"
    return redirect(auth_url)


def _oidc_csrf_error_response():
    state = request.args.get("state")
    expected_state = session.pop("oidc_state", None)
    if (
        not state
        or not expected_state
        or not secrets.compare_digest(state, expected_state)
    ):
        return "Authentication error: CSRF state verification failed", 400
    return None


def _oidc_fetch_userinfo(code):
    config = get_oidc_config()
    token_endpoint = config.get("token_endpoint")
    userinfo_endpoint = config.get("userinfo_endpoint")
    if not token_endpoint:
        return None, ("Error: OIDC token endpoint not configured", 500)

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": get_oidc_redirect_uri(),
        "client_id": get_oidc_client_id(),
        "client_secret": get_oidc_client_secret(),
    }
    token_res = requests.post(token_endpoint, data=payload, timeout=15)
    token_res.raise_for_status()
    token_data = token_res.json()

    access_token = token_data.get("access_token")
    if not access_token:
        return None, ("Error: OIDC token response did not contain access_token", 500)
    if not userinfo_endpoint:
        return None, ("Error: OIDC userinfo endpoint not configured", 500)

    userinfo_res = requests.get(
        userinfo_endpoint,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    userinfo_res.raise_for_status()
    return userinfo_res.json(), None


def _oidc_email_verified(userinfo_data):
    verified = userinfo_data.get("email_verified")
    if verified is True:
        return True
    if isinstance(verified, str) and verified.strip().lower() in ("true", "1", "yes"):
        return True
    return False


def _oidc_resolve_identity(userinfo_data):
    email_claim = userinfo_data.get("email")
    if email_claim:
        if not _oidc_email_verified(userinfo_data):
            return None, (
                render_template(
                    "login.html",
                    error=(
                        "Your identity provider has not verified this email address. "
                        "Please verify it with your provider and try again."
                    ),
                ),
                403,
            )
        email = email_claim.lower().strip()
    else:
        fallback = userinfo_data.get("sub") or userinfo_data.get("preferred_username")
        if not fallback:
            return None, ("Error: User identification claim not found in userinfo", 500)
        email = str(fallback).lower().strip()

    user_groups = userinfo_data.get("groups", [])
    if not isinstance(user_groups, list):
        user_groups = []
    is_admin = (email in get_oidc_admin_users()) or (
        get_oidc_admin_group() in user_groups
    )
    return (email, is_admin), None


def _oidc_sync_user_access(email, is_admin):
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, is_admin FROM users WHERE email = ?", (email,))
            user_row = cursor.fetchone()

            if is_admin:
                if not user_row:
                    cursor.execute(
                        "INSERT INTO users (email, is_admin) VALUES (?, 1)",
                        (email,),
                    )
                else:
                    cursor.execute(
                        "UPDATE users SET is_admin = 1 WHERE email = ?", (email,)
                    )
                conn.commit()
            elif not user_row:
                return None, render_template(
                    "login.html",
                    error="You do not have access to this tool. Please contact an administrator.",
                )
        return user_row, None
    except Exception as db_err:
        current_app.logger.error(
            f"Failed to query/insert OIDC user in database: {db_err}"
        )
        return None, (
            render_template(
                "login.html",
                error="Sign-in is temporarily unavailable. Please try again later.",
            ),
            503,
        )


@auth_bp.route("/oidc/callback")
def oidc_callback():
    if not is_oidc_enabled():
        return redirect(url_for("home"))

    csrf_error = _oidc_csrf_error_response()
    if csrf_error:
        return csrf_error

    code = request.args.get("code")
    if not code:
        return "Authentication error: Missing authorization code", 400

    try:
        userinfo, fetch_error = _oidc_fetch_userinfo(code)
        if fetch_error:
            return fetch_error[0], fetch_error[1]

        identity, identity_error = _oidc_resolve_identity(userinfo)
        if identity_error:
            return identity_error[0], identity_error[1]

        email, is_admin = identity
        user_row, access_error = _oidc_sync_user_access(email, is_admin)
        if access_error:
            return access_error

        start_user_session(
            build_session_user(
                email,
                is_admin or bool(user_row and user_row[1]),
            )
        )

        write_audit_log("auth.login", email, email, {"method": "oidc"})
        return redirect(url_for("home"))
    except Exception as e:
        current_app.logger.error(f"OIDC flow callback failure: {e}")
        return render_template(
            "login.html",
            error="Authentication failed. Please try again or contact an administrator.",
        ), 500
