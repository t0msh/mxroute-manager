"""Backward-compatible re-exports from utils.apprise package."""

from utils.apprise import (
    BUILDER_SERVICES,
    SERVICE_BY_ID,
    SERVICE_CRED_ENV,
    builder_catalog_for_api,
    compile_service_url,
    cred_env_keys_for_api,
    format_env_cred_snippet,
    format_env_snippet,
    infer_service_id_from_url,
    mask_apprise_url,
    parse_service_url,
    resolve_target_url,
    service_label_from_url,
    validate_apprise_url,
)
from utils.apprise.secrets import inject_secret_into_url as _inject_secret_into_url

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
    "_inject_secret_into_url",
]
