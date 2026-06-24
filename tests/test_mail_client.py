"""Tests for domain mail client settings."""

from unittest.mock import patch

from services.mail_client import build_domain_mail_client_settings

DOMAIN = "Example.COM"


def test_build_domain_mail_client_settings_normalizes_domain():
    with patch(
        "services.mail_client.webmail_health_check",
        return_value={"status": "skipped"},
    ):
        settings = build_domain_mail_client_settings(DOMAIN)

    assert settings["domain"] == "example.com"
    assert settings["mail_host"] == "mail.example.com"
    assert settings["imap"] == {
        "host": "mail.example.com",
        "port": 993,
        "encryption": "ssl",
    }
    assert settings["smtp_ssl"]["port"] == 465
    assert settings["smtp_starttls"]["port"] == 587


def test_webmail_url_when_dns_passes():
    with patch(
        "services.mail_client.webmail_health_check",
        return_value={"status": "pass"},
    ):
        settings = build_domain_mail_client_settings("example.com")

    assert settings["webmail"]["url"] == "https://webmail.example.com"
    assert settings["webmail"]["status"] == "pass"


def test_webmail_url_omitted_when_not_deployed():
    with patch(
        "services.mail_client.webmail_health_check",
        return_value={"status": "skipped"},
    ):
        settings = build_domain_mail_client_settings("example.com")

    assert settings["webmail"]["url"] is None
    assert settings["webmail"]["status"] == "skipped"
