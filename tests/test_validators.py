"""Tests for input validation helpers (pure logic, no I/O)."""

import pytest

from utils.validators import (
    validate_domain,
    validate_username,
    validate_local_user_identifier,
    is_oidc_user_identifier,
    requires_local_password,
    validate_mailbox_password,
    validate_subdomain_prefix,
    validate_recovery_email,
)


@pytest.mark.parametrize(
    "domain,expected",
    [
        ("example.com", True),
        ("mail.example.co.uk", True),
        ("", False),
        (None, False),
        ("not-a-domain", False),
        ("-bad.com", False),
    ],
)
def test_validate_domain(domain, expected):
    assert validate_domain(domain) is expected


@pytest.mark.parametrize(
    "username,expected",
    [
        ("alex", True),
        ("alex.smith", True),
        ("alex_smith", True),
        ("", False),
        ("bad space", False),
        ("user@domain", False),
    ],
)
def test_validate_username(username, expected):
    assert validate_username(username) is expected


@pytest.mark.parametrize(
    "identifier,expected",
    [
        ("billy", True),
        ("user@local", True),
        ("admin@example.com", True),
        ("", False),
        ("bad space", False),
    ],
)
def test_validate_local_user_identifier(identifier, expected):
    assert validate_local_user_identifier(identifier) is expected


def test_oidc_identifier_rules():
    assert is_oidc_user_identifier("admin@example.com", oidc_enabled=True) is True
    assert is_oidc_user_identifier("billy", oidc_enabled=True) is False
    assert is_oidc_user_identifier("admin@example.com", oidc_enabled=False) is False


def test_requires_local_password():
    assert requires_local_password("billy", oidc_enabled=True) is True
    assert requires_local_password("admin@example.com", oidc_enabled=True) is False
    assert requires_local_password("billy", oidc_enabled=False) is True


@pytest.mark.parametrize(
    "password,expected",
    [
        ("Abcd123!", True),
        ("weak", False),
        ("NoDigits!", False),
        ("nodigits1", False),
        ("", False),
    ],
)
def test_validate_mailbox_password(password, expected):
    assert validate_mailbox_password(password) is expected


def test_validate_subdomain_prefix_reserved_and_format():
    ok, _ = validate_subdomain_prefix("reset")
    assert ok is True

    ok, message = validate_subdomain_prefix("mail")
    assert ok is False
    assert "reserved" in message.lower()

    ok, message = validate_subdomain_prefix("-bad")
    assert ok is False


def test_validate_recovery_email_rules():
    ok, _ = validate_recovery_email("user@example.com", "backup@gmail.com")
    assert ok is True

    ok, message = validate_recovery_email("user@example.com", "user@example.com")
    assert ok is False
    assert "differ" in message.lower()

    ok, message = validate_recovery_email("user@example.com", "")
    assert ok is False
