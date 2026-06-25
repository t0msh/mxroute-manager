import re

import dns.exception
import dns.resolver

_SPF_INCLUDE_RE = re.compile(
    r"include:((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,})",
    re.IGNORECASE,
)


def _normalize_txt(value):
    return value.strip().strip('"').replace(" ", "").lower()


def _txt_strings(record):
    parts = []
    for part in record.strings:
        if isinstance(part, bytes):
            parts.append(part.decode("utf-8", errors="replace"))
        else:
            parts.append(str(part))
    return "".join(parts)


def _query_txt(name):
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 5.0
    try:
        answers = resolver.resolve(name, "TXT")
        return [_txt_strings(record) for record in answers]
    except (
        dns.resolver.NXDOMAIN,
        dns.resolver.NoAnswer,
        dns.resolver.NoNameservers,
        dns.exception.Timeout,
    ):
        return []
    except Exception:
        return []


def _query_mx(domain):
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 5.0
    try:
        answers = resolver.resolve(domain, "MX")
        records = []
        for record in answers:
            host = str(record.exchange).lower().rstrip(".")
            records.append({"priority": int(record.preference), "hostname": host})
        return sorted(records, key=lambda item: (item["priority"], item["hostname"]))
    except (
        dns.resolver.NXDOMAIN,
        dns.resolver.NoAnswer,
        dns.resolver.NoNameservers,
        dns.exception.Timeout,
    ):
        return []
    except Exception:
        return []


def _check_status(passed, optional=False):
    if passed:
        return "pass"
    return "warn" if optional else "fail"


MAIL_DNS_CHECK_KEYS = ("mx", "spf", "dkim", "dmarc")


def overall_from_checks(checks, exclude_keys=None):
    exclude = set(exclude_keys or ())
    statuses = [
        check["status"]
        for key, check in checks.items()
        if key not in exclude and check.get("status") not in ("skipped",)
    ]
    if any(status == "fail" for status in statuses):
        return "unhealthy"
    if any(status == "warn" for status in statuses):
        return "degraded"
    return "healthy"


def apply_mail_hosting_context(health, mail_hosting_enabled):
    """When mail hosting is disabled, mail DNS checks are informational only."""
    health["mail_hosting_enabled"] = bool(mail_hosting_enabled)
    if mail_hosting_enabled:
        return health

    checks = health.setdefault("checks", {})
    for key in MAIL_DNS_CHECK_KEYS:
        if key not in checks:
            continue
        checks[key] = {
            **checks[key],
            "status": "skipped",
            "message": "Mail hosting is disabled — this record is not required",
        }
    health["overall"] = overall_from_checks(checks)
    return health


def dkim_record_parts(dkim_data, domain):
    """Resolve MXroute's relative DKIM host (e.g. x._domainkey) to a public DNS FQDN."""
    domain = domain.lower().rstrip(".")
    dkim_name = str(dkim_data.get("name", f"x._domainkey.{domain}")).lower().rstrip(".")
    if dkim_name.endswith(f".{domain}"):
        host_part = dkim_name[: -(len(domain) + 1)]
        fqdn = dkim_name
    else:
        host_part = dkim_name
        fqdn = f"{host_part}.{domain}"
    return host_part, fqdn


def _dkim_public_key(value):
    norm = _normalize_txt(value)
    for segment in norm.split(";"):
        if segment.startswith("p="):
            return segment[2:]
    return None


def _spf_includes(spf_norm):
    return [
        f"include:{match.group(1).lower()}"
        for match in _SPF_INCLUDE_RE.finditer(spf_norm)
    ]


def _spf_covers_expected(expected_spf_norm, found_spf_norm):
    required = _spf_includes(expected_spf_norm)
    if not required:
        return "v=spf1" in found_spf_norm
    return all(include in found_spf_norm for include in required)


def _spf_match_result(expected_spf_norm, spf_records):
    if not spf_records:
        return False, "SPF record missing or does not match"
    if expected_spf_norm and expected_spf_norm in spf_records:
        return True, "SPF record matches MXroute"
    if expected_spf_norm and any(
        _spf_covers_expected(expected_spf_norm, found) for found in spf_records
    ):
        return True, "SPF includes required MXroute mechanisms"
    if any("v=spf1" in record for record in spf_records):
        return False, "SPF record missing required MXroute mechanisms"
    return False, "SPF record missing or does not match"


def _is_valid_dmarc(record_norm):
    return "v=dmarc1" in record_norm and ";p=" in f";{record_norm}"


def _dkim_matches(expected_value, found_values):
    expected_norm = _normalize_txt(expected_value)
    found_norms = [_normalize_txt(value) for value in found_values]
    if expected_norm and expected_norm in found_norms:
        return True
    expected_key = _dkim_public_key(expected_value)
    if not expected_key:
        return bool(found_norms)
    return any(_dkim_public_key(value) == expected_key for value in found_values)


def _mx_health_check(domain, expected_dns):
    expected_mx = []
    for mx in expected_dns.get("mx_records") or []:
        expected_mx.append(
            {
                "priority": int(mx.get("priority") or 0),
                "hostname": str(mx.get("hostname", "")).lower().rstrip("."),
            }
        )
    expected_mx.sort(key=lambda item: (item["priority"], item["hostname"]))
    found_mx = _query_mx(domain)
    mx_pass = expected_mx == found_mx if expected_mx else bool(found_mx)
    return {
        "status": _check_status(mx_pass),
        "label": "MX Records",
        "expected": expected_mx,
        "found": found_mx,
        "message": "MX records match MXroute"
        if mx_pass
        else "MX records missing or incorrect",
    }


def _spf_health_check(domain, expected_dns):
    expected_spf = ""
    if expected_dns.get("spf"):
        expected_spf = expected_dns["spf"].get("value", "")
    spf_records = [
        _normalize_txt(txt)
        for txt in _query_txt(domain)
        if txt.lower().startswith("v=spf1")
    ]
    expected_spf_norm = _normalize_txt(expected_spf) if expected_spf else ""
    spf_pass, spf_message = _spf_match_result(expected_spf_norm, spf_records)
    return {
        "status": _check_status(spf_pass),
        "label": "SPF (TXT)",
        "expected": expected_spf or "v=spf1 include:mxroute.com -all",
        "found": spf_records,
        "message": spf_message,
    }


def _dkim_health_check(domain, expected_dns):
    dkim_data = expected_dns.get("dkim") or {}
    _, dkim_fqdn = dkim_record_parts(dkim_data, domain)
    expected_dkim = dkim_data.get("value", "")
    dkim_records_raw = _query_txt(dkim_fqdn)
    dkim_records = [_normalize_txt(txt) for txt in dkim_records_raw]
    dkim_pass = _dkim_matches(expected_dkim, dkim_records_raw)
    return {
        "status": _check_status(dkim_pass, optional=True),
        "label": "DKIM (TXT)",
        "expected_host": dkim_fqdn,
        "expected": expected_dkim,
        "found": dkim_records,
        "message": "DKIM record present"
        if dkim_pass
        else "DKIM record missing or does not match",
    }


def _dmarc_health_check(domain, dmarc_expected, dmarc_exact_match=False):
    dmarc_host = f"_dmarc.{domain}"
    dmarc_expected_value = (
        dmarc_expected or "v=DMARC1; p=none; sp=none; adkim=r; aspf=r;"
    )
    dmarc_records = [
        _normalize_txt(txt)
        for txt in _query_txt(dmarc_host)
        if "v=dmarc1" in _normalize_txt(txt)
    ]
    dmarc_expected_norm = _normalize_txt(dmarc_expected_value)

    if not dmarc_records:
        status = "warn"
        message = "DMARC record missing"
    elif dmarc_expected_norm in dmarc_records:
        status = "pass"
        message = (
            "DMARC record matches custom policy"
            if dmarc_exact_match
            else "DMARC record matches default policy"
        )
    elif dmarc_exact_match:
        status = "warn"
        message = "DMARC record missing or does not match custom policy"
    elif any(_is_valid_dmarc(record) for record in dmarc_records):
        status = "warn"
        message = "DMARC record present (differs from default template)"
    else:
        status = "warn"
        message = "DMARC record missing or invalid"

    return {
        "status": status,
        "label": "DMARC (TXT)",
        "expected_host": dmarc_host,
        "expected": dmarc_expected_value,
        "found": dmarc_records,
        "message": message,
        "custom_policy": dmarc_exact_match,
    }


def _verification_health_check(domain, verification_record):
    verify_name = str(verification_record.get("name", "")).strip()
    verify_value = str(verification_record.get("value", "")).strip()
    verify_fqdn = f"{verify_name}.{domain}".lower() if verify_name else domain
    verify_records = [_normalize_txt(txt) for txt in _query_txt(verify_fqdn)]
    verify_pass = (
        _normalize_txt(verify_value) in verify_records if verify_value else False
    )
    return {
        "status": _check_status(verify_pass, optional=True),
        "label": "Domain Verification (TXT)",
        "expected_host": verify_fqdn,
        "expected": verify_value,
        "found": verify_records,
        "message": "Verification TXT present"
        if verify_pass
        else "Verification TXT missing",
    }


def check_dns_health(
    domain,
    expected_dns,
    verification_record=None,
    dmarc_expected=None,
    dmarc_exact_match=False,
):
    """Compare live public DNS against MXroute-provided expectations."""
    domain = domain.lower().strip()
    checks = {
        "mx": _mx_health_check(domain, expected_dns),
        "spf": _spf_health_check(domain, expected_dns),
        "dkim": _dkim_health_check(domain, expected_dns),
        "dmarc": _dmarc_health_check(
            domain, dmarc_expected, dmarc_exact_match=dmarc_exact_match
        ),
    }
    if verification_record:
        checks["verification"] = _verification_health_check(domain, verification_record)

    return {
        "domain": domain,
        "overall": overall_from_checks(checks),
        "checks": checks,
    }
