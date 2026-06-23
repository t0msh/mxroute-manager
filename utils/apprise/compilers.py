from urllib.parse import quote, urlparse

from utils.apprise.fields import (
    field_bool,
    field_text,
    parse_header_fields,
    query_params,
)


def compile_ntfy(fields):
    topic = field_text(fields, "topic")
    if not topic:
        raise ValueError("Topic is required")

    host = field_text(fields, "host") or "ntfy.sh"
    secure = field_bool(fields, "secure", True)
    scheme = "ntfys" if secure else "ntfy"
    token = field_text(fields, "token")

    auth = ""
    if token:
        auth = f"{quote(token, safe='')}@"

    params = query_params(
        auth="token" if token else None,
        priority=field_text(fields, "priority") or None,
        tags=field_text(fields, "tags") or None,
    )
    suffix = f"?{params}" if params else ""
    return f"{scheme}://{auth}{host}/{quote(topic, safe='')}{suffix}"


def compile_json_webhook(fields):
    raw_url = field_text(fields, "url")
    if not raw_url:
        raise ValueError("Webhook URL is required")

    parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
    if not parsed.hostname:
        raise ValueError("Invalid webhook URL")

    secure = parsed.scheme in ("https", "jsons") or field_bool(fields, "secure", True)
    scheme = "jsons" if secure else "json"
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    token = field_text(fields, "token")
    auth = ""
    if token:
        auth = f":{quote(token, safe='')}@"
    elif parsed.username:
        password = parsed.password or ""
        auth = f"{quote(parsed.username, safe='')}:{quote(password, safe='')}@"

    extra = query_params(**{f"+{k}": v for k, v in parse_header_fields(fields).items()})
    if extra:
        path = f"{path}{'&' if '?' in path else '?'}{extra}"

    return f"{scheme}://{auth}{parsed.hostname}{port}{path}"


def compile_discord(fields):
    webhook_id = field_text(fields, "webhook_id")
    webhook_token = field_text(fields, "webhook_token")
    if not webhook_id or not webhook_token:
        raise ValueError("Webhook ID and token are required")
    return f"discord://{quote(webhook_id, safe='')}/{quote(webhook_token, safe='')}"


def compile_slack(fields):
    webhook_url = field_text(fields, "webhook_url")
    if not webhook_url:
        raise ValueError("Slack webhook URL is required")
    parsed = urlparse(webhook_url)
    if "hooks.slack.com" not in (parsed.netloc or ""):
        raise ValueError("Expected a Slack incoming webhook URL")
    path = (parsed.path or "").strip("/")
    if not path.startswith("services/"):
        raise ValueError("Invalid Slack webhook URL path")
    tokens = path.split("/")[1:]
    if len(tokens) < 2:
        raise ValueError("Invalid Slack webhook URL")
    return f"slack://{'/'.join(quote(t, safe='') for t in tokens)}"


def compile_gotify(fields):
    host = field_text(fields, "host")
    token = field_text(fields, "token")
    if not host or not token:
        raise ValueError("Server and application token are required")
    secure = field_bool(fields, "secure", True)
    scheme = "gotifys" if secure else "gotify"
    port = field_text(fields, "port")
    port_suffix = f":{port}" if port else ""
    return f"{scheme}://{quote(host, safe='')}{port_suffix}/{quote(token, safe='')}"


def compile_pushover(fields):
    user_key = field_text(fields, "user_key")
    api_token = field_text(fields, "api_token")
    if not user_key or not api_token:
        raise ValueError("User key and API token are required")
    return f"pover://{quote(user_key, safe='')}@{quote(api_token, safe='')}"


def compile_telegram(fields):
    bot_token = field_text(fields, "bot_token")
    chat_id = field_text(fields, "chat_id")
    if not bot_token or not chat_id:
        raise ValueError("Bot token and chat ID are required")
    return f"tgram://{quote(bot_token, safe='')}/{quote(chat_id, safe='')}"


def compile_mailto(fields):
    to_email = field_text(fields, "to_email")
    if not to_email:
        raise ValueError("Recipient email is required")

    if field_bool(fields, "use_reset_smtp"):
        from services.mail import is_smtp_configured, smtp_config_from_settings

        config = smtp_config_from_settings()
        if not is_smtp_configured(config):
            raise ValueError(
                "Mailbox Password Reset SMTP is not fully configured in Settings"
            )
        smtp_host = config["host"]
        smtp_user = config["user"]
        smtp_password = config["password"]
        port = config["port"]
        from_email = (
            field_text(fields, "from_email") or config["from_address"] or smtp_user
        )
    else:
        smtp_host = field_text(fields, "smtp_host")
        smtp_user = field_text(fields, "smtp_user")
        smtp_password = field_text(fields, "smtp_password")
        if not all([smtp_host, smtp_user, smtp_password]):
            raise ValueError("SMTP host, user, and password are required")
        port = field_text(fields, "smtp_port") or "587"
        from_email = field_text(fields, "from_email") or smtp_user

    params = query_params(**{"from": from_email, "to": to_email})
    return (
        f"mailto://{quote(smtp_user, safe='')}:{quote(smtp_password, safe='')}"
        f"@{quote(smtp_host, safe='')}:{port}?{params}"
    )


def compile_custom(fields):
    url = field_text(fields, "url")
    if not url:
        raise ValueError("Apprise URL is required")
    return url
