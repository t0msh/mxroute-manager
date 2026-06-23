MAIL_DNS_RECORD_TYPES = ("mx", "spf", "dkim", "dmarc")
DNS_RECORD_TYPES = ("verification",) + MAIL_DNS_RECORD_TYPES
# webmail is deployable/checkable but opt-in: never auto-included by fix-all.
DEPLOYABLE_RECORD_TYPES = DNS_RECORD_TYPES + ("webmail",)

PENDING_MAIL_CHECK = {
    "status": "pending",
    "label": "",
    "message": "MXroute provides this record after the domain is registered (Step 3).",
}


def webmail_host(domain):
    return f"webmail.{domain.lower().strip()}"


def get_webmail_target():
    """MXroute server hostname the webmail CNAME points at (DNS-only)."""
    from models.db import get_config_value

    return (get_config_value("MX_SERVER") or "").strip().lower().rstrip(".")
