import secrets

from flask import session

from models.db import (
    get_admin_user,
    get_oidc_admin_users,
    load_domain_mapping,
    load_user_grants,
)


def build_session_user(email, is_admin=False):
    email = email.lower()
    mapping = load_domain_mapping()
    delegated_domains = mapping.get(email, [])
    domain_grants = load_user_grants().get(email, {})
    resolved_admin = bool(
        is_admin
        or email in get_oidc_admin_users()
        or email == get_admin_user()
        or "*" in delegated_domains
    )
    return {
        "email": email,
        "is_admin": resolved_admin,
        "delegated_domains": delegated_domains,
        "domain_grants": domain_grants,
    }


def start_user_session(user):
    """Establish an authenticated session, rotating session + CSRF state on login."""
    session.clear()
    session["user"] = user
    session["csrf_token"] = secrets.token_urlsafe(32)
