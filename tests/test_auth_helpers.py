"""Unit tests for permission and admin checks in utils.auth_helpers."""

from utils.auth_helpers import (
    has_permission,
    has_domain_access,
    has_any_permission,
    is_user_admin,
)


def _delegate(email="editor@local", domain="example.com", permissions=None):
    permissions = permissions or ["dashboard", "emails"]
    return {
        "email": email,
        "is_admin": False,
        "delegated_domains": [domain],
        "domain_grants": {domain: permissions},
    }


def test_admin_user_has_full_access():
    user = {"email": "admin@local", "is_admin": True, "domain_grants": {}}
    assert is_user_admin(user) is True
    assert has_domain_access(user, "example.com") is True
    assert has_permission(user, "example.com", "emails") is True
    assert has_permission(user, "other.com", "spam") is True


def test_delegate_has_only_assigned_permissions():
    user = _delegate(permissions=["dashboard"])
    assert has_permission(user, "example.com", "dashboard") is True
    assert has_permission(user, "example.com", "emails") is False
    assert has_any_permission(user, "example.com", "dashboard", "emails") is True
    assert has_any_permission(user, "example.com", "forwarders", "spam") is False


def test_delegate_cannot_access_other_domains():
    user = _delegate()
    assert has_domain_access(user, "example.com") is True
    assert has_domain_access(user, "other.com") is False
    assert has_permission(user, "other.com", "emails") is False


def test_missing_user_denied():
    assert has_permission(None, "example.com", "emails") is False
    assert has_domain_access(None, "example.com") is False
    assert is_user_admin(None) is False


def test_unknown_permission_denied_for_delegate():
    user = _delegate(permissions=["emails"])
    assert has_permission(user, "example.com", "not-a-real-perm") is False
