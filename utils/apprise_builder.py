"""Apprise URL builder schemas and server-side URL compilation."""

import os
from urllib.parse import parse_qs, quote, unquote, urlparse

import apprise

_NTFY_PRIORITIES = ("min", "low", "default", "high", "urgent", "max")

# Per-service env var for token-only storage (see docs/notifications.md).
SERVICE_CRED_ENV = {
    "ntfy": "APPRISE_CRED_NTFY",
    "json": "APPRISE_CRED_JSON",
    "discord": "APPRISE_CRED_DISCORD",
    "gotify": "APPRISE_CRED_GOTIFY",
    "pushover": "APPRISE_CRED_PUSHOVER",
    "telegram": "APPRISE_CRED_TELEGRAM",
    "mailto": "APPRISE_CRED_SMTP",
}


def _field_text(fields, key, default=""):
    value = fields.get(key, default)
    return str(value or "").strip()


def _field_bool(fields, key, default=False):
    value = fields.get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1", "yes", "on")


def _query_params(**pairs):
    parts = []
    for key, value in pairs.items():
        if value is None or value == "":
            continue
        parts.append(f"{quote(str(key), safe='')}={quote(str(value), safe='')}")
    return "&".join(parts)


def _compile_ntfy(fields):
    topic = _field_text(fields, "topic")
    if not topic:
        raise ValueError("Topic is required")

    host = _field_text(fields, "host") or "ntfy.sh"
    secure = _field_bool(fields, "secure", True)
    scheme = "ntfys" if secure else "ntfy"
    token = _field_text(fields, "token")

    auth = ""
    if token:
        auth = f"{quote(token, safe='')}@"

    params = _query_params(
        auth="token" if token else None,
        priority=_field_text(fields, "priority") or None,
        tags=_field_text(fields, "tags") or None,
    )
    suffix = f"?{params}" if params else ""
    return f"{scheme}://{auth}{host}/{quote(topic, safe='')}{suffix}"


def _compile_json_webhook(fields):
    raw_url = _field_text(fields, "url")
    if not raw_url:
        raise ValueError("Webhook URL is required")

    parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
    if not parsed.hostname:
        raise ValueError("Invalid webhook URL")

    secure = parsed.scheme in ("https", "jsons") or _field_bool(fields, "secure", True)
    scheme = "jsons" if secure else "json"
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    token = _field_text(fields, "token")
    auth = ""
    if token:
        auth = f":{quote(token, safe='')}@"
    elif parsed.username:
        password = parsed.password or ""
        auth = f"{quote(parsed.username, safe='')}:{quote(password, safe='')}@"

    extra = _query_params(
        **{f"+{k}": v for k, v in _parse_header_fields(fields).items()}
    )
    if extra:
        path = f"{path}{'&' if '?' in path else '?'}{extra}"

    return f"{scheme}://{auth}{parsed.hostname}{port}{path}"


def _parse_header_fields(fields):
    headers = {}
    raw = _field_text(fields, "auth_header")
    if raw:
        if ":" in raw:
            name, value = raw.split(":", 1)
            headers[name.strip()] = value.strip()
        else:
            headers["Authorization"] = f"Bearer {raw}"
    return headers


def _compile_discord(fields):
    webhook_id = _field_text(fields, "webhook_id")
    webhook_token = _field_text(fields, "webhook_token")
    if not webhook_id or not webhook_token:
        raise ValueError("Webhook ID and token are required")
    return f"discord://{quote(webhook_id, safe='')}/{quote(webhook_token, safe='')}"


def _compile_slack(fields):
    webhook_url = _field_text(fields, "webhook_url")
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


def _compile_gotify(fields):
    host = _field_text(fields, "host")
    token = _field_text(fields, "token")
    if not host or not token:
        raise ValueError("Server and application token are required")
    secure = _field_bool(fields, "secure", True)
    scheme = "gotifys" if secure else "gotify"
    port = _field_text(fields, "port")
    port_suffix = f":{port}" if port else ""
    return f"{scheme}://{quote(host, safe='')}{port_suffix}/{quote(token, safe='')}"


def _compile_pushover(fields):
    user_key = _field_text(fields, "user_key")
    api_token = _field_text(fields, "api_token")
    if not user_key or not api_token:
        raise ValueError("User key and API token are required")
    return f"pover://{quote(user_key, safe='')}@{quote(api_token, safe='')}"


def _compile_telegram(fields):
    bot_token = _field_text(fields, "bot_token")
    chat_id = _field_text(fields, "chat_id")
    if not bot_token or not chat_id:
        raise ValueError("Bot token and chat ID are required")
    return f"tgram://{quote(bot_token, safe='')}/{quote(chat_id, safe='')}"


def _compile_mailto(fields):
    to_email = _field_text(fields, "to_email")
    if not to_email:
        raise ValueError("Recipient email is required")

    if _field_bool(fields, "use_reset_smtp"):
        from models.db import (
            get_reset_smtp_from,
            get_reset_smtp_host,
            get_reset_smtp_password,
            get_reset_smtp_port,
            get_reset_smtp_user,
        )
        from services.mail import is_smtp_configured, smtp_config_from_settings

        config = smtp_config_from_settings()
        if not is_smtp_configured(config):
            raise ValueError("Mailbox Password Reset SMTP is not fully configured in Settings")
        smtp_host = config["host"]
        smtp_user = config["user"]
        smtp_password = config["password"]
        port = config["port"]
        from_email = _field_text(fields, "from_email") or config["from_address"] or smtp_user
    else:
        smtp_host = _field_text(fields, "smtp_host")
        smtp_user = _field_text(fields, "smtp_user")
        smtp_password = _field_text(fields, "smtp_password")
        if not all([smtp_host, smtp_user, smtp_password]):
            raise ValueError("SMTP host, user, and password are required")
        port = _field_text(fields, "smtp_port") or "587"
        from_email = _field_text(fields, "from_email") or smtp_user

    params = _query_params(**{"from": from_email, "to": to_email})
    return (
        f"mailto://{quote(smtp_user, safe='')}:{quote(smtp_password, safe='')}"
        f"@{quote(smtp_host, safe='')}:{port}?{params}"
    )


def _compile_custom(fields):
    url = _field_text(fields, "url")
    if not url:
        raise ValueError("Apprise URL is required")
    return url


BUILDER_SERVICES = [
    {
        "id": "ntfy",
        "label": "ntfy",
        "description": "Self-hosted or ntfy.sh push notifications",
        "fields": [
            {"id": "host", "label": "Server", "type": "text", "placeholder": "ntfy.sh"},
            {"id": "topic", "label": "Topic", "type": "text", "required": True},
            {"id": "token", "label": "Auth token", "type": "secret"},
            {"id": "priority", "label": "Priority", "type": "select", "options": list(_NTFY_PRIORITIES), "default": "default"},
            {"id": "tags", "label": "Tags", "type": "text", "placeholder": "mxroute,alert"},
            {"id": "secure", "label": "Use HTTPS", "type": "checkbox", "default": True},
        ],
        "compile": _compile_ntfy,
    },
    {
        "id": "json",
        "label": "JSON Webhook",
        "description": "Generic HTTP JSON webhook (Apprise json://)",
        "fields": [
            {"id": "url", "label": "Webhook URL", "type": "text", "required": True, "placeholder": "https://hooks.example.com/mxroute"},
            {"id": "token", "label": "Bearer token", "type": "secret"},
            {"id": "auth_header", "label": "Auth header (optional)", "type": "secret", "placeholder": "Authorization: Bearer ..."},
            {"id": "secure", "label": "Use HTTPS", "type": "checkbox", "default": True},
        ],
        "compile": _compile_json_webhook,
    },
    {
        "id": "discord",
        "label": "Discord",
        "description": "Discord webhook",
        "fields": [
            {"id": "webhook_id", "label": "Webhook ID", "type": "text", "required": True},
            {"id": "webhook_token", "label": "Webhook token", "type": "secret", "required": True},
        ],
        "compile": _compile_discord,
    },
    {
        "id": "slack",
        "label": "Slack",
        "description": "Slack incoming webhook",
        "fields": [
            {"id": "webhook_url", "label": "Incoming webhook URL", "type": "text", "required": True},
        ],
        "compile": _compile_slack,
    },
    {
        "id": "gotify",
        "label": "Gotify",
        "description": "Gotify push notifications",
        "fields": [
            {"id": "host", "label": "Server", "type": "text", "required": True},
            {"id": "port", "label": "Port", "type": "text", "placeholder": "443"},
            {"id": "token", "label": "Application token", "type": "secret", "required": True},
            {"id": "secure", "label": "Use HTTPS", "type": "checkbox", "default": True},
        ],
        "compile": _compile_gotify,
    },
    {
        "id": "pushover",
        "label": "Pushover",
        "description": "Pushover notifications",
        "fields": [
            {"id": "user_key", "label": "User key", "type": "text", "required": True},
            {"id": "api_token", "label": "API token", "type": "secret", "required": True},
        ],
        "compile": _compile_pushover,
    },
    {
        "id": "telegram",
        "label": "Telegram",
        "description": "Telegram bot notifications",
        "fields": [
            {"id": "bot_token", "label": "Bot token", "type": "secret", "required": True},
            {"id": "chat_id", "label": "Chat ID", "type": "text", "required": True},
        ],
        "compile": _compile_telegram,
    },
    {
        "id": "mailto",
        "label": "Email (SMTP)",
        "description": "Email via SMTP",
        "fields": [
            {"id": "use_reset_smtp", "label": "Use Mailbox Password Reset SMTP settings", "type": "checkbox", "default": False},
            {"id": "smtp_host", "label": "SMTP host", "type": "text"},
            {"id": "smtp_port", "label": "SMTP port", "type": "text", "default": "587"},
            {"id": "smtp_user", "label": "SMTP user", "type": "text"},
            {"id": "smtp_password", "label": "SMTP password", "type": "secret"},
            {"id": "from_email", "label": "From address", "type": "text"},
            {"id": "to_email", "label": "To address", "type": "text", "required": True},
        ],
        "compile": _compile_mailto,
    },
    {
        "id": "custom",
        "label": "Custom Apprise URL",
        "description": "Paste any Apprise URL (see appriseit.com)",
        "fields": [
            {"id": "url", "label": "Apprise URL", "type": "text", "required": True},
        ],
        "compile": _compile_custom,
    },
]

_SERVICE_BY_ID = {service["id"]: service for service in BUILDER_SERVICES}


def builder_catalog_for_api():
    """Return service definitions without compile callables."""
    catalog = []
    for service in BUILDER_SERVICES:
        catalog.append({
            "id": service["id"],
            "label": service["label"],
            "description": service.get("description", ""),
            "fields": service["fields"],
        })
    return catalog


def compile_service_url(service_id, fields, *, token_in_env=False):
    service = _SERVICE_BY_ID.get(service_id)
    if not service:
        raise ValueError(f"Unknown service: {service_id}")
    if not isinstance(fields, dict):
        raise ValueError("Fields must be an object")

    if token_in_env and service_id == "mailto" and _field_bool(fields, "use_reset_smtp"):
        token_in_env = False

    fields_for_compile = dict(fields)
    secret_value = _extract_service_secret(service_id, fields_for_compile) if token_in_env else ""

    if token_in_env:
        _clear_service_secrets(service_id, fields_for_compile)

    url = service["compile"](fields_for_compile)
    validate_apprise_url(_resolve_url_with_cred(url, SERVICE_CRED_ENV.get(service_id), secret_value))

    cred_env = SERVICE_CRED_ENV.get(service_id) if token_in_env and secret_value else None
    env_snippet = format_env_cred_snippet(cred_env, secret_value) if cred_env else None

    return {
        "url": url,
        "masked_url": mask_apprise_url(url),
        "service": service_id,
        "cred_env": cred_env,
        "env_snippet": env_snippet,
    }


def _extract_service_secret(service_id, fields):
    if service_id == "ntfy":
        return _field_text(fields, "token")
    if service_id == "json":
        return _field_text(fields, "token") or _field_text(fields, "auth_header")
    if service_id == "discord":
        return _field_text(fields, "webhook_token")
    if service_id == "gotify":
        return _field_text(fields, "token")
    if service_id == "pushover":
        return _field_text(fields, "api_token")
    if service_id == "telegram":
        return _field_text(fields, "bot_token")
    if service_id == "mailto" and not _field_bool(fields, "use_reset_smtp"):
        return _field_text(fields, "smtp_password")
    return ""


def _clear_service_secrets(service_id, fields):
    if service_id == "ntfy":
        fields["token"] = ""
    elif service_id == "json":
        fields["token"] = ""
        fields["auth_header"] = ""
    elif service_id == "discord":
        fields["webhook_token"] = ""
    elif service_id == "gotify":
        fields["token"] = ""
    elif service_id == "pushover":
        fields["api_token"] = ""
    elif service_id == "telegram":
        fields["bot_token"] = ""
    elif service_id == "mailto":
        fields["smtp_password"] = ""


def _resolve_url_with_cred(url, cred_env, inline_secret=None):
    secret = (inline_secret or "").strip()
    if not secret and cred_env:
        secret = (os.getenv(cred_env) or "").strip()
    if not secret or not url:
        return url
    return _inject_secret_into_url(url, secret)


def _inject_secret_into_url(url, secret):
    url = str(url or "").strip()
    if not url or "://" not in url:
        return url

    scheme, rest = url.split("://", 1)
    scheme_lower = scheme.lower()

    if scheme_lower in ("ntfy", "ntfys"):
        if "@" in rest:
            _, host_part = rest.split("@", 1)
            return f"{scheme}://{quote(secret, safe='')}@{host_part}"
        return f"{scheme}://{quote(secret, safe='')}@{rest}"

    if scheme_lower == "discord":
        if "/" in rest:
            webhook_id, _ = rest.split("/", 1)
            return f"{scheme}://{webhook_id}/{quote(secret, safe='')}"
        return url

    if scheme_lower in ("gotify", "gotifys"):
        if "/" in rest:
            host_part, _ = rest.split("/", 1)
            return f"{scheme}://{host_part}/{quote(secret, safe='')}"
        return url

    if scheme_lower == "pover":
        if "@" in rest:
            user_key, _ = rest.split("@", 1)
            return f"{scheme}://{user_key}@{quote(secret, safe='')}"
        return url

    if scheme_lower == "tgram":
        if "/" in rest:
            _, chat_id = rest.split("/", 1)
            return f"{scheme}://{quote(secret, safe='')}/{chat_id}"
        return url

    if scheme_lower in ("json", "jsons"):
        if rest.startswith(":") and "@" in rest:
            _, host_part = rest.split("@", 1)
            return f"{scheme}://:{quote(secret, safe='')}@{host_part}"
        return f"{scheme}://:{quote(secret, safe='')}@{rest}"

    if scheme_lower == "mailto":
        if "@" in rest:
            creds, host_part = rest.split("@", 1)
            if ":" in creds:
                user, _ = creds.split(":", 1)
                return f"{scheme}://{quote(user, safe='')}:{quote(secret, safe='')}@{host_part}"
        return url

    return url


def resolve_target_url(target):
    """Build a deliverable Apprise URL from a stored target."""
    url = str((target or {}).get("url") or "").strip()
    cred_env = str((target or {}).get("cred_env") or "").strip() or None
    return _resolve_url_with_cred(url, cred_env)


def format_env_cred_snippet(cred_env, secret_value):
    if not cred_env or not secret_value:
        return ""
    return f"{cred_env}={secret_value}"


def cred_env_keys_for_api():
    return dict(SERVICE_CRED_ENV)


def validate_apprise_url(url):
    url = str(url or "").strip()
    if not url:
        raise ValueError("URL is required")
    apobj = apprise.Apprise()
    if not apobj.add(url):
        raise ValueError("Invalid or unsupported Apprise URL")
    return url


def format_env_snippet(url, cred_env=None, secret_value=None):
    if cred_env and secret_value:
        return format_env_cred_snippet(cred_env, secret_value)
    return ""


def mask_apprise_url(url):
    """Mask credentials in an Apprise URL for API responses."""
    url = str(url or "").strip()
    if not url or "://" not in url:
        return url

    scheme, rest = url.split("://", 1)
    if "@" in rest:
        _, host_part = rest.split("@", 1)
        return f"{scheme}://***@{host_part}"

    # Path-based secrets (discord://id/token, slack://a/b/c)
    if "/" in rest:
        head, tail = rest.split("/", 1)
        if tail:
            return f"{scheme}://{head}/***"

    return url


def service_label_from_url(url):
    """Best-effort service name from URL scheme."""
    return infer_service_id_from_url(url)


def infer_service_id_from_url(url):
    """Map an Apprise URL scheme to a builder service id."""
    url = str(url or "").strip()
    if "://" not in url:
        return "custom"
    scheme = url.split("://", 1)[0].lower()
    mapping = {
        "ntfy": "ntfy",
        "ntfys": "ntfy",
        "json": "json",
        "jsons": "json",
        "discord": "discord",
        "slack": "slack",
        "gotify": "gotify",
        "gotifys": "gotify",
        "pover": "pushover",
        "tgram": "telegram",
        "mailto": "mailto",
    }
    return mapping.get(scheme, "custom")


def _masked_credential(value):
    return not value or str(value).strip() == "***"


def _cred_from_env(cred_env):
    if not cred_env:
        return ""
    return (os.getenv(cred_env) or "").strip()


def _parse_ntfy(url, *, cred_env=None):
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    secure = scheme != "ntfy"

    token = ""
    if parsed.username and not _masked_credential(parsed.username):
        token = unquote(parsed.username)

    host = parsed.hostname or ""
    if parsed.port and parsed.port not in (80, 443):
        host = f"{host}:{parsed.port}"

    topic = unquote((parsed.path or "").lstrip("/"))
    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

    if not token and cred_env:
        token = _cred_from_env(cred_env)

    return {
        "host": host or "ntfy.sh",
        "topic": topic,
        "token": token,
        "priority": params.get("priority", "default"),
        "tags": params.get("tags", ""),
        "secure": secure,
    }


def _parse_json(url, *, cred_env=None):
    parsed = urlparse(url)
    secure = parsed.scheme.lower() == "jsons"

    token = ""
    if parsed.password and not _masked_credential(parsed.password):
        token = unquote(parsed.password)
    if not token and cred_env:
        token = _cred_from_env(cred_env)

    port = f":{parsed.port}" if parsed.port else ""
    webhook = f"{'https' if secure else 'http'}://{parsed.hostname or ''}{port}{parsed.path or '/'}"
    if parsed.query:
        webhook = f"{webhook}?{parsed.query}"

    return {
        "url": webhook,
        "token": token,
        "auth_header": "",
        "secure": secure,
    }


def _parse_discord(url, *, cred_env=None):
    parsed = urlparse(url)
    path = (parsed.path or "").strip("/")
    parts = path.split("/", 1)
    webhook_id = unquote(parts[0]) if parts else ""
    webhook_token = ""
    if len(parts) > 1 and not _masked_credential(parts[1]):
        webhook_token = unquote(parts[1])
    if not webhook_token and cred_env:
        webhook_token = _cred_from_env(cred_env)
    return {"webhook_id": webhook_id, "webhook_token": webhook_token}


def _parse_slack(url, *, cred_env=None):
    return {"webhook_url": ""}


def _parse_gotify(url, *, cred_env=None):
    parsed = urlparse(url)
    secure = parsed.scheme.lower() == "gotifys"
    host = parsed.hostname or ""
    port = str(parsed.port) if parsed.port else ""
    path_token = (parsed.path or "").strip("/")
    token = ""
    if path_token and not _masked_credential(path_token):
        token = unquote(path_token)
    if not token and cred_env:
        token = _cred_from_env(cred_env)
    return {"host": host, "port": port, "token": token, "secure": secure}


def _parse_pushover(url, *, cred_env=None):
    parsed = urlparse(url)
    user_key = unquote(parsed.username or "")
    api_token = unquote(parsed.hostname or "")
    if _masked_credential(api_token):
        api_token = ""
    if not api_token and cred_env:
        api_token = _cred_from_env(cred_env)
    return {"user_key": user_key, "api_token": api_token}


def _parse_telegram(url, *, cred_env=None):
    parsed = urlparse(url)
    path = (parsed.path or "").strip("/")
    parts = path.split("/", 1)
    bot_token = unquote(parts[0]) if parts and not _masked_credential(parts[0]) else ""
    chat_id = unquote(parts[1]) if len(parts) > 1 else ""
    if not bot_token and cred_env:
        bot_token = _cred_from_env(cred_env)
    return {"bot_token": bot_token, "chat_id": chat_id}


def _parse_mailto(url, *, cred_env=None):
    parsed = urlparse(url)
    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    smtp_user = unquote(parsed.username or "") if parsed.username else ""
    smtp_password = ""
    if parsed.password and not _masked_credential(parsed.password):
        smtp_password = unquote(parsed.password)
    host_part = parsed.hostname or ""
    port = str(parsed.port) if parsed.port else "587"
    if not smtp_password and cred_env:
        smtp_password = _cred_from_env(cred_env)
    return {
        "use_reset_smtp": False,
        "smtp_host": host_part,
        "smtp_port": port,
        "smtp_user": smtp_user,
        "smtp_password": smtp_password,
        "from_email": params.get("from", ""),
        "to_email": params.get("to", ""),
    }


def _parse_custom(url, *, cred_env=None):
    return {"url": url}


_PARSE_BY_SERVICE = {
    "ntfy": _parse_ntfy,
    "json": _parse_json,
    "discord": _parse_discord,
    "slack": _parse_slack,
    "gotify": _parse_gotify,
    "pushover": _parse_pushover,
    "telegram": _parse_telegram,
    "mailto": _parse_mailto,
    "custom": _parse_custom,
}


def parse_service_url(service_id, url, *, cred_env=None):
    """Reverse an Apprise URL into builder form fields."""
    url = str(url or "").strip()
    if not url:
        raise ValueError("URL is required")

    service_id = str(service_id or "").strip() or infer_service_id_from_url(url)
    if service_id not in _SERVICE_BY_ID:
        service_id = infer_service_id_from_url(url)

    parser = _PARSE_BY_SERVICE.get(service_id)
    if not parser:
        raise ValueError(f"Cannot parse URL for service: {service_id}")

    fields = parser(url, cred_env=cred_env)
    return {
        "service": service_id,
        "fields": fields,
        "url": url,
        "masked_url": mask_apprise_url(url),
        "cred_env": cred_env,
    }

