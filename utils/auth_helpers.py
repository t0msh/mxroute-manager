import time
import threading
import requests
from flask import session, jsonify, current_app
from functools import wraps

from models.db import (
    get_oidc_discovery_url,
    get_oidc_admin_users,
    get_admin_user,
    load_domain_mapping,
    load_user_grants,
    ALL_PERMISSIONS,
)
from utils.validators import validate_domain

_oidc_config = None
_oidc_config_fetched_at = 0.0
_oidc_config_lock = threading.Lock()
_OIDC_CONFIG_TTL = 3600


def get_oidc_config():
    global _oidc_config, _oidc_config_fetched_at
    now = time.monotonic()
    if _oidc_config is not None and (now - _oidc_config_fetched_at) < _OIDC_CONFIG_TTL:
        return _oidc_config
    discovery_url = get_oidc_discovery_url()
    if not discovery_url:
        raise ValueError("OIDC_DISCOVERY_URL is not configured")
    with _oidc_config_lock:
        now = time.monotonic()
        if (
            _oidc_config is not None
            and (now - _oidc_config_fetched_at) < _OIDC_CONFIG_TTL
        ):
            return _oidc_config
        try:
            res = requests.get(discovery_url, timeout=10)
            res.raise_for_status()
            _oidc_config = res.json()
            _oidc_config_fetched_at = time.monotonic()
            return _oidc_config
        except Exception as e:
            current_app.logger.error(f"Failed to fetch OIDC configuration: {e}")
            raise


def clear_oidc_config_cache():
    global _oidc_config, _oidc_config_fetched_at
    with _oidc_config_lock:
        _oidc_config = None
        _oidc_config_fetched_at = 0.0


def get_current_user():
    return session.get("user")


def is_user_admin(user):
    if not user:
        return False
    email_val = user.get("email")
    email = email_val.lower() if isinstance(email_val, str) else ""
    if email in get_oidc_admin_users() or email == get_admin_user():
        return True
    mapping = load_domain_mapping()
    if "*" in mapping.get(email, []):
        return True
    return user.get("is_admin", False)


def _user_email(user):
    email_val = user.get("email") if user else None
    return email_val.lower() if isinstance(email_val, str) else ""


def get_domain_grants(user):
    if not user:
        return {}
    cached = user.get("domain_grants")
    if isinstance(cached, dict):
        return cached
    email = _user_email(user)
    return load_user_grants().get(email, {})


def has_domain_access(user, domain):
    if not user:
        return False
    if is_user_admin(user):
        return True
    grants = get_domain_grants(user)
    return domain.lower() in grants


def has_permission(user, domain, permission):
    if not user:
        return False
    if is_user_admin(user):
        return True
    if permission not in ALL_PERMISSIONS:
        return False
    grants = get_domain_grants(user)
    domain_permissions = grants.get(domain.lower(), [])
    return permission in domain_permissions


def has_any_permission(user, domain, *permissions):
    if not user:
        return False
    if is_user_admin(user):
        return True
    return any(has_permission(user, domain, permission) for permission in permissions)


def _forbidden_domain_message(domain):
    return jsonify(
        {
            "success": False,
            "error": {
                "message": f"Forbidden: You do not have access to domain '{domain}'"
            },
        }
    ), 403


def _forbidden_permission_message(permission):
    return jsonify(
        {
            "success": False,
            "error": {
                "message": f"Forbidden: Missing '{permission}' permission for this domain"
            },
        }
    ), 403


def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user or not is_user_admin(user):
            return jsonify(
                {
                    "success": False,
                    "error": {"message": "Forbidden: Admin access required"},
                }
            ), 403
        return f(*args, **kwargs)

    return decorated_function


def require_domain_access(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        domain = kwargs.get("domain")
        if domain:
            if not validate_domain(domain):
                return jsonify(
                    {
                        "success": False,
                        "error": {"message": "Invalid domain name format"},
                    }
                ), 400
            user = get_current_user()
            if not user or not has_domain_access(user, domain):
                return _forbidden_domain_message(domain)
        return f(*args, **kwargs)

    return decorated_function


def require_permission(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            domain = kwargs.get("domain")
            if domain:
                if not validate_domain(domain):
                    return jsonify(
                        {
                            "success": False,
                            "error": {"message": "Invalid domain name format"},
                        }
                    ), 400
                user = get_current_user()
                if not user or not has_permission(user, domain, permission):
                    if user and has_domain_access(user, domain):
                        return _forbidden_permission_message(permission)
                    return _forbidden_domain_message(domain)
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def require_any_permission(*permissions):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            domain = kwargs.get("domain")
            if domain:
                if not validate_domain(domain):
                    return jsonify(
                        {
                            "success": False,
                            "error": {"message": "Invalid domain name format"},
                        }
                    ), 400
                user = get_current_user()
                if not user or not has_any_permission(user, domain, *permissions):
                    if user and has_domain_access(user, domain):
                        return jsonify(
                            {
                                "success": False,
                                "error": {
                                    "message": "Forbidden: Insufficient permissions for this domain"
                                },
                            }
                        ), 403
                    return _forbidden_domain_message(domain)
            return f(*args, **kwargs)

        return decorated_function

    return decorator
