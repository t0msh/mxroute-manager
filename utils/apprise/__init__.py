"""Apprise URL builder schemas and server-side URL compilation."""

from utils.apprise.catalog import (
    BUILDER_SERVICES,
    SERVICE_BY_ID,
    builder_catalog_for_api,
)
from utils.apprise.fields import field_bool
from utils.apprise.parsers import PARSE_BY_SERVICE
from utils.apprise.secrets import (
    SERVICE_CRED_ENV,
    clear_service_secrets,
    cred_env_keys_for_api,
    extract_service_secret,
    format_env_cred_snippet,
    resolve_target_url,
    resolve_url_with_cred,
)
from utils.apprise.url_utils import (
    format_env_snippet,
    infer_service_id_from_url,
    mask_apprise_url,
    service_label_from_url,
    validate_apprise_url,
)

__all__ = [
    "BUILDER_SERVICES",
    "SERVICE_BY_ID",
    "SERVICE_CRED_ENV",
    "builder_catalog_for_api",
    "compile_service_url",
    "cred_env_keys_for_api",
    "format_env_cred_snippet",
    "format_env_snippet",
    "infer_service_id_from_url",
    "mask_apprise_url",
    "parse_service_url",
    "resolve_target_url",
    "service_label_from_url",
    "validate_apprise_url",
]


def compile_service_url(service_id, fields, *, token_in_env=False):
    service = SERVICE_BY_ID.get(service_id)
    if not service:
        raise ValueError(f"Unknown service: {service_id}")
    if not isinstance(fields, dict):
        raise ValueError("Fields must be an object")

    if token_in_env and service_id == "mailto" and field_bool(fields, "use_reset_smtp"):
        token_in_env = False

    fields_for_compile = dict(fields)
    secret_value = (
        extract_service_secret(service_id, fields_for_compile) if token_in_env else ""
    )

    if token_in_env:
        clear_service_secrets(service_id, fields_for_compile)

    url = service["compile"](fields_for_compile)
    validate_apprise_url(
        resolve_url_with_cred(url, SERVICE_CRED_ENV.get(service_id), secret_value)
    )

    cred_env = (
        SERVICE_CRED_ENV.get(service_id) if token_in_env and secret_value else None
    )
    env_snippet = format_env_cred_snippet(cred_env, secret_value) if cred_env else None

    return {
        "url": url,
        "masked_url": mask_apprise_url(url),
        "service": service_id,
        "cred_env": cred_env,
        "env_snippet": env_snippet,
    }


def parse_service_url(service_id, url, *, cred_env=None):
    """Reverse an Apprise URL into builder form fields."""
    url = str(url or "").strip()
    if not url:
        raise ValueError("URL is required")

    service_id = str(service_id or "").strip() or infer_service_id_from_url(url)
    if service_id not in SERVICE_BY_ID:
        service_id = infer_service_id_from_url(url)

    parser = PARSE_BY_SERVICE.get(service_id)
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
