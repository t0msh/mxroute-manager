import dns.exception
import dns.resolver


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
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout):
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
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout):
        return []
    except Exception:
        return []


def _check_status(passed, optional=False):
    if passed:
        return "pass"
    return "warn" if optional else "fail"


def check_dns_health(domain, expected_dns, verification_record=None, dmarc_expected=None):
    """Compare live public DNS against MXroute-provided expectations."""
    domain = domain.lower().strip()
    checks = {}

    expected_mx = []
    for mx in expected_dns.get("mx_records") or []:
        expected_mx.append({
            "priority": int(mx.get("priority") or 0),
            "hostname": str(mx.get("hostname", "")).lower().rstrip("."),
        })
    expected_mx.sort(key=lambda item: (item["priority"], item["hostname"]))
    found_mx = _query_mx(domain)
    mx_pass = expected_mx == found_mx if expected_mx else bool(found_mx)
    checks["mx"] = {
        "status": _check_status(mx_pass),
        "label": "MX Records",
        "expected": expected_mx,
        "found": found_mx,
        "message": "MX records match MXroute" if mx_pass else "MX records missing or incorrect",
    }

    expected_spf = ""
    if expected_dns.get("spf"):
        expected_spf = expected_dns["spf"].get("value", "")
    spf_records = [_normalize_txt(txt) for txt in _query_txt(domain) if txt.lower().startswith("v=spf1")]
    expected_spf_norm = _normalize_txt(expected_spf) if expected_spf else ""
    spf_pass = expected_spf_norm in spf_records if expected_spf_norm else any("v=spf1" in r for r in spf_records)
    checks["spf"] = {
        "status": _check_status(spf_pass),
        "label": "SPF (TXT)",
        "expected": expected_spf or "v=spf1 include:mxroute.com -all",
        "found": spf_records,
        "message": "SPF record present" if spf_pass else "SPF record missing or does not match",
    }

    dkim_data = expected_dns.get("dkim") or {}
    dkim_name = str(dkim_data.get("name") or f"x._domainkey.{domain}").lower().rstrip(".")
    expected_dkim = dkim_data.get("value", "")
    dkim_records = [_normalize_txt(txt) for txt in _query_txt(dkim_name)]
    expected_dkim_norm = _normalize_txt(expected_dkim) if expected_dkim else ""
    dkim_pass = expected_dkim_norm in dkim_records if expected_dkim_norm else bool(dkim_records)
    checks["dkim"] = {
        "status": _check_status(dkim_pass, optional=True),
        "label": "DKIM (TXT)",
        "expected_host": dkim_name,
        "expected": expected_dkim,
        "found": dkim_records,
        "message": "DKIM record present" if dkim_pass else "DKIM record missing or does not match",
    }

    dmarc_host = f"_dmarc.{domain}"
    dmarc_expected_value = dmarc_expected or "v=DMARC1; p=none; sp=none; adkim=r; aspf=r;"
    dmarc_records = [_normalize_txt(txt) for txt in _query_txt(dmarc_host) if "v=dmarc1" in _normalize_txt(txt)]
    dmarc_expected_norm = _normalize_txt(dmarc_expected_value)
    dmarc_pass = dmarc_expected_norm in dmarc_records if dmarc_records else False
    if not dmarc_records:
        dmarc_pass = False
    checks["dmarc"] = {
        "status": _check_status(dmarc_pass, optional=True),
        "label": "DMARC (TXT)",
        "expected_host": dmarc_host,
        "expected": dmarc_expected_value,
        "found": dmarc_records,
        "message": "DMARC record present" if dmarc_pass else "DMARC record missing or does not match",
    }

    if verification_record:
        verify_name = str(verification_record.get("name", "")).strip()
        verify_value = str(verification_record.get("value", "")).strip()
        verify_fqdn = f"{verify_name}.{domain}".lower() if verify_name else domain
        verify_records = [_normalize_txt(txt) for txt in _query_txt(verify_fqdn)]
        verify_pass = _normalize_txt(verify_value) in verify_records if verify_value else False
        checks["verification"] = {
            "status": _check_status(verify_pass, optional=True),
            "label": "Domain Verification (TXT)",
            "expected_host": verify_fqdn,
            "expected": verify_value,
            "found": verify_records,
            "message": "Verification TXT present" if verify_pass else "Verification TXT missing",
        }

    statuses = [check["status"] for check in checks.values()]
    if any(status == "fail" for status in statuses):
        overall = "unhealthy"
    elif any(status == "warn" for status in statuses):
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "domain": domain,
        "overall": overall,
        "checks": checks,
    }
