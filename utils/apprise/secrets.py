import os
from urllib.parse import quote

from utils.apprise.fields import field_bool, field_text

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

_SERVICE_SECRET_EXTRACTORS = {
    "ntfy": lambda fields: field_text(fields, "token"),
    "json": lambda fields: (
        field_text(fields, "token") or field_text(fields, "auth_header")
    ),
    "discord": lambda fields: field_text(fields, "webhook_token"),
    "gotify": lambda fields: field_text(fields, "token"),
    "pushover": lambda fields: field_text(fields, "api_token"),
    "telegram": lambda fields: field_text(fields, "bot_token"),
}

_SERVICE_SECRET_FIELD_CLEARS = {
    "ntfy": ("token",),
    "json": ("token", "auth_header"),
    "discord": ("webhook_token",),
    "gotify": ("token",),
    "pushover": ("api_token",),
    "telegram": ("bot_token",),
    "mailto": ("smtp_password",),
}


def extract_service_secret(service_id, fields):
    if service_id == "mailto" and not field_bool(fields, "use_reset_smtp"):
        return field_text(fields, "smtp_password")
    extractor = _SERVICE_SECRET_EXTRACTORS.get(service_id)
    return extractor(fields) if extractor else ""


def clear_service_secrets(service_id, fields):
    for key in _SERVICE_SECRET_FIELD_CLEARS.get(service_id, ()):
        fields[key] = ""


def resolve_url_with_cred(url, cred_env, inline_secret=None):
    secret = (inline_secret or "").strip()
    if not secret and cred_env:
        secret = (os.getenv(cred_env) or "").strip()
    if not secret or not url:
        return url
    return inject_secret_into_url(url, secret)


def inject_secret_into_url(url, secret):
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
                return (
                    f"{scheme}://{quote(user, safe='')}:{quote(secret, safe='')}"
                    f"@{host_part}"
                )
        return url

    return url


def resolve_target_url(target):
    """Build a deliverable Apprise URL from a stored target."""
    url = str((target or {}).get("url") or "").strip()
    cred_env = str((target or {}).get("cred_env") or "").strip() or None
    return resolve_url_with_cred(url, cred_env)


def format_env_cred_snippet(cred_env, secret_value):
    if not cred_env or not secret_value:
        return ""
    return f"{cred_env}={secret_value}"


def cred_env_keys_for_api():
    return dict(SERVICE_CRED_ENV)
