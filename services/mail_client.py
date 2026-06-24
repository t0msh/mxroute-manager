"""Mail client connection settings for MXroute-hosted domains."""

from services.cloudflare_constants import webmail_public_url
from services.cloudflare_health import webmail_health_check


def build_domain_mail_client_settings(domain):
    """Return IMAP/SMTP/webmail settings for onboarding mail users."""
    domain = domain.strip().lower().rstrip(".")
    mail_host = f"mail.{domain}"
    webmail_url = webmail_public_url(domain)
    webmail_check = webmail_health_check(domain)
    webmail_status = webmail_check.get("status") or "skipped"

    return {
        "domain": domain,
        "mail_host": mail_host,
        "username_note": "Use your full email address as the username.",
        "imap": {"host": mail_host, "port": 993, "encryption": "ssl"},
        "smtp_ssl": {"host": mail_host, "port": 465, "encryption": "ssl"},
        "smtp_starttls": {"host": mail_host, "port": 587, "encryption": "starttls"},
        "webmail": {
            "url": webmail_url if webmail_status in ("pass", "pending") else None,
            "status": webmail_status,
        },
    }
