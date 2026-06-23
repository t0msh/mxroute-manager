import apprise

from utils.apprise.secrets import format_env_cred_snippet


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
