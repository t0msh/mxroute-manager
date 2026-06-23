"""Cloudflare DNS integration — public API re-exported for backward compatibility."""

from models.db import get_config_value, get_dmarc_record
from services.cloudflare_api import (
    cf_is_configured,
    cf_request,
    ensure_cf_zone,
    fetch_cf_dns_sets,
    find_cf_zone_id,
)
from services.cloudflare_constants import (
    DEPLOYABLE_RECORD_TYPES,
    DNS_RECORD_TYPES,
    MAIL_DNS_RECORD_TYPES,
    PENDING_MAIL_CHECK,
    get_webmail_target,
    webmail_host,
)
from services.cloudflare_deploy import (
    CfDeployContext,
    deploy_dns_record_to_cf,
    deploy_missing_dns_to_cf,
)
from services.cloudflare_dns import public_dns_resolves as _public_dns_resolves
from services.cloudflare_health import (
    build_setup_health,
    webmail_health_check as _webmail_health_check,
)
from services.cloudflare_portal import (
    check_reset_portal_dns,
    deploy_reset_portal_cname,
    remove_reset_portal_cname,
)
from services.cloudflare_records import cf_upsert_cname, cf_upsert_txt
from services.mxroute import audit

__all__ = [
    "DEPLOYABLE_RECORD_TYPES",
    "DNS_RECORD_TYPES",
    "MAIL_DNS_RECORD_TYPES",
    "PENDING_MAIL_CHECK",
    "_public_dns_resolves",
    "_webmail_health_check",
    "audit",
    "build_setup_health",
    "cf_is_configured",
    "cf_request",
    "cf_upsert_cname",
    "cf_upsert_txt",
    "check_reset_portal_dns",
    "CfDeployContext",
    "deploy_dns_record_to_cf",
    "deploy_missing_dns_to_cf",
    "deploy_reset_portal_cname",
    "ensure_cf_zone",
    "fetch_cf_dns_sets",
    "find_cf_zone_id",
    "get_config_value",
    "get_dmarc_record",
    "get_webmail_target",
    "remove_reset_portal_cname",
    "webmail_host",
]
