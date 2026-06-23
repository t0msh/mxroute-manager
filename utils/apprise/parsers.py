import os
from urllib.parse import parse_qs, unquote, urlparse


def masked_credential(value):
    return not value or str(value).strip() == "***"


def cred_from_env(cred_env):
    if not cred_env:
        return ""
    return (os.getenv(cred_env) or "").strip()


def parse_ntfy(url, *, cred_env=None):
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    secure = scheme != "ntfy"

    token = ""
    if parsed.username and not masked_credential(parsed.username):
        token = unquote(parsed.username)

    host = parsed.hostname or ""
    if parsed.port and parsed.port not in (80, 443):
        host = f"{host}:{parsed.port}"

    topic = unquote((parsed.path or "").lstrip("/"))
    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

    if not token and cred_env:
        token = cred_from_env(cred_env)

    return {
        "host": host or "ntfy.sh",
        "topic": topic,
        "token": token,
        "priority": params.get("priority", "default"),
        "tags": params.get("tags", ""),
        "secure": secure,
    }


def parse_json(url, *, cred_env=None):
    parsed = urlparse(url)
    secure = parsed.scheme.lower() == "jsons"

    token = ""
    if parsed.password and not masked_credential(parsed.password):
        token = unquote(parsed.password)
    if not token and cred_env:
        token = cred_from_env(cred_env)

    port = f":{parsed.port}" if parsed.port else ""
    webhook = (
        f"{'https' if secure else 'http'}://{parsed.hostname or ''}"
        f"{port}{parsed.path or '/'}"
    )
    if parsed.query:
        webhook = f"{webhook}?{parsed.query}"

    return {
        "url": webhook,
        "token": token,
        "auth_header": "",
        "secure": secure,
    }


def parse_discord(url, *, cred_env=None):
    parsed = urlparse(url)
    path = (parsed.path or "").strip("/")
    parts = path.split("/", 1)
    webhook_id = unquote(parts[0]) if parts else ""
    webhook_token = ""
    if len(parts) > 1 and not masked_credential(parts[1]):
        webhook_token = unquote(parts[1])
    if not webhook_token and cred_env:
        webhook_token = cred_from_env(cred_env)
    return {"webhook_id": webhook_id, "webhook_token": webhook_token}


def parse_slack(url, *, cred_env=None):
    return {"webhook_url": ""}


def parse_gotify(url, *, cred_env=None):
    parsed = urlparse(url)
    secure = parsed.scheme.lower() == "gotifys"
    host = parsed.hostname or ""
    port = str(parsed.port) if parsed.port else ""
    path_token = (parsed.path or "").strip("/")
    token = ""
    if path_token and not masked_credential(path_token):
        token = unquote(path_token)
    if not token and cred_env:
        token = cred_from_env(cred_env)
    return {"host": host, "port": port, "token": token, "secure": secure}


def parse_pushover(url, *, cred_env=None):
    parsed = urlparse(url)
    user_key = unquote(parsed.username or "")
    api_token = unquote(parsed.hostname or "")
    if masked_credential(api_token):
        api_token = ""
    if not api_token and cred_env:
        api_token = cred_from_env(cred_env)
    return {"user_key": user_key, "api_token": api_token}


def parse_telegram(url, *, cred_env=None):
    parsed = urlparse(url)
    path = (parsed.path or "").strip("/")
    parts = path.split("/", 1)
    bot_token = unquote(parts[0]) if parts and not masked_credential(parts[0]) else ""
    chat_id = unquote(parts[1]) if len(parts) > 1 else ""
    if not bot_token and cred_env:
        bot_token = cred_from_env(cred_env)
    return {"bot_token": bot_token, "chat_id": chat_id}


def parse_mailto(url, *, cred_env=None):
    parsed = urlparse(url)
    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    smtp_user = unquote(parsed.username or "") if parsed.username else ""
    smtp_password = ""
    if parsed.password and not masked_credential(parsed.password):
        smtp_password = unquote(parsed.password)
    host_part = parsed.hostname or ""
    port = str(parsed.port) if parsed.port else "587"
    if not smtp_password and cred_env:
        smtp_password = cred_from_env(cred_env)
    return {
        "use_reset_smtp": False,
        "smtp_host": host_part,
        "smtp_port": port,
        "smtp_user": smtp_user,
        "smtp_password": smtp_password,
        "from_email": params.get("from", ""),
        "to_email": params.get("to", ""),
    }


def parse_custom(url, *, cred_env=None):
    return {"url": url}


PARSE_BY_SERVICE = {
    "ntfy": parse_ntfy,
    "json": parse_json,
    "discord": parse_discord,
    "slack": parse_slack,
    "gotify": parse_gotify,
    "pushover": parse_pushover,
    "telegram": parse_telegram,
    "mailto": parse_mailto,
    "custom": parse_custom,
}
