import smtplib
from email.message import EmailMessage

from models.db import (
    get_reset_smtp_from,
    get_reset_smtp_host,
    get_reset_smtp_password,
    get_reset_smtp_port,
    get_reset_smtp_user,
    is_mailbox_reset_enabled,
    reset_smtp_use_tls,
)
from utils.audit_log import write_audit_log


def smtp_config_from_settings():
    return {
        "host": get_reset_smtp_host(),
        "port": get_reset_smtp_port(),
        "user": get_reset_smtp_user(),
        "password": get_reset_smtp_password(),
        "from_address": get_reset_smtp_from(),
        "use_tls": reset_smtp_use_tls(),
    }


def smtp_config_from_overrides(data):
    saved = smtp_config_from_settings()
    overrides = data or {}
    # RESET_SMTP_PASSWORD is env-only and never accepted from the request body.
    password = saved["password"]

    port_raw = overrides.get("RESET_SMTP_PORT", saved["port"])
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        port = saved["port"]

    use_tls_raw = overrides.get("RESET_SMTP_USE_TLS", saved["use_tls"])
    if isinstance(use_tls_raw, bool):
        use_tls = use_tls_raw
    else:
        use_tls = str(use_tls_raw).lower() in ("true", "1", "yes")

    return {
        "host": str(overrides.get("RESET_SMTP_HOST", saved["host"] or "")).strip(),
        "port": port,
        "user": str(overrides.get("RESET_SMTP_USER", saved["user"] or "")).strip(),
        "password": password,
        "from_address": str(
            overrides.get("RESET_SMTP_FROM", saved["from_address"] or "")
        ).strip(),
        "use_tls": use_tls,
    }


def is_smtp_configured(config=None):
    config = config or smtp_config_from_settings()
    return bool(
        config.get("host")
        and config.get("from_address")
        and config.get("user")
        and config.get("password")
    )


def is_password_reset_available():
    return is_mailbox_reset_enabled() and is_smtp_configured()


def send_email(to_address, subject, body, smtp_config=None):
    config = smtp_config or smtp_config_from_settings()
    if not is_smtp_configured(config):
        raise ValueError("SMTP is not configured")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["from_address"]
    message["To"] = to_address
    message.set_content(body)

    try:
        with smtplib.SMTP(config["host"], config["port"], timeout=30) as smtp:
            if config.get("use_tls"):
                smtp.starttls()
            if config.get("user") and config.get("password"):
                smtp.login(config["user"], config["password"])
            smtp.send_message(message)
        return True
    except Exception as exc:
        write_audit_log(
            "smtp.send_failed",
            "system",
            to_address,
            {"subject": subject, "error": str(exc)},
        )
        raise


def smtp_config_with_from(smtp_config=None, from_address=None):
    config = dict(smtp_config or smtp_config_from_settings())
    if from_address:
        config["from_address"] = from_address
    return config


def send_password_reset_email(
    recovery_email,
    mailbox_email,
    reset_url,
    smtp_config=None,
    from_address=None,
):
    body = "\n".join(
        [
            "You requested a password reset for your mailbox.",
            "",
            f"Mailbox: {mailbox_email}",
            "",
            "To choose a new password, open this link (valid for 1 hour):",
            reset_url,
            "",
            "If you did not request this, you can ignore this email.",
        ]
    )
    send_email(
        recovery_email,
        "Reset your mailbox password",
        body,
        smtp_config=smtp_config_with_from(smtp_config, from_address),
    )


def send_test_email(recipient, smtp_config=None):
    body = "\n".join(
        [
            "This is a test email from MXroute Manager.",
            "",
            "Your SMTP settings appear to be working correctly.",
        ]
    )
    send_email(
        recipient,
        "MXroute Manager SMTP test",
        body,
        smtp_config=smtp_config,
    )
