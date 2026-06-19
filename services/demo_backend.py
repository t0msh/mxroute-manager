"""In-memory fake MXroute / Cloudflare / NPM state for DEMO_MODE."""

import copy
import re
import threading
import uuid

from models.db import get_dmarc_record
from services.demo_mode import DEMO_DOMAINS, MX_DNS_TEMPLATE, VERIFY_RECORD, is_demo_domain
from services.dns_health import overall_from_checks

_lock = threading.Lock()
_next_id = 1000


def _new_id(prefix="demo"):
    global _next_id
    _next_id += 1
    return f"{prefix}-{_next_id}"


def _mailbox(username, *, quota=1024, limit=500, usage=64.0, sent=12, suspended=False):
    return {
        "username": username.lower(),
        "quota": int(quota),
        "limit": int(limit),
        "usage": float(usage),
        "sent": int(sent),
        "suspended": bool(suspended),
    }


def _empty_domain(*, mail_hosting=True, dns_deployed=False, cf_zone_id=None):
    return {
        "mail_hosting": mail_hosting,
        "dns_deployed": dns_deployed,
        "cf_zone_id": cf_zone_id,
        "email_accounts": {},
        "forwarders": {},
        "pointers": [],
        "catch_all": {"type": "fail", "address": None},
        "spam": {"high_score": 5, "whitelist": [], "blacklist": []},
    }


def _dkim_parts(dkim_data, domain):
    domain = domain.lower().rstrip(".")
    dkim_name = str(dkim_data.get("name", f"x._domainkey.{domain}")).lower().rstrip(".")
    if dkim_name.endswith(f".{domain}"):
        fqdn = dkim_name
    else:
        fqdn = f"{dkim_name}.{domain}"
    return dkim_name, fqdn


def _seed_state():
    example = _empty_domain(dns_deployed=True, cf_zone_id="demo-zone-example-com")
    example["email_accounts"] = {
        "hello": _mailbox("hello", usage=128.5, sent=42),
        "support": _mailbox("support", quota=2048, limit=1000, usage=512.0, sent=8),
    }
    example["forwarders"] = {
        "info": {"alias": "info", "destinations": ["support@example.com"]},
    }
    example["pointers"] = [{"pointer": "other.example.org", "type": "alias"}]

    notreal = _empty_domain(dns_deployed=True, cf_zone_id="demo-zone-notarealsite-org")
    notreal["email_accounts"] = {
        "admin": _mailbox("admin", usage=32.0, sent=3),
    }

    demo_net = _empty_domain(dns_deployed=False)

    zones = {
        "demo-zone-example-com": {
            "name": "example.com",
            "records": _demo_mail_records("example.com"),
        },
        "demo-zone-notarealsite-org": {
            "name": "notarealsite.org",
            "records": _demo_mail_records("notarealsite.org"),
        },
    }

    return {
        "domains": {
            "example.com": example,
            "notarealsite.org": notreal,
            "demo.net": demo_net,
        },
        "cf_zones": zones,
        "npm_proxy_hosts": [],
        "npm_certificates": [],
    }


def _demo_mail_records(domain):
    dns = copy.deepcopy(MX_DNS_TEMPLATE)
    records = []
    for mx in dns["mx_records"]:
        records.append({
            "id": _new_id("rec"),
            "type": "MX",
            "name": domain,
            "content": mx["hostname"],
            "priority": mx["priority"],
        })
    records.append({
        "id": _new_id("rec"),
        "type": "TXT",
        "name": domain,
        "content": dns["spf"]["value"],
    })
    host_part, fqdn = _dkim_parts(dns["dkim"], domain)
    records.append({
        "id": _new_id("rec"),
        "type": "TXT",
        "name": fqdn,
        "content": dns["dkim"]["value"],
    })
    records.append({
        "id": _new_id("rec"),
        "type": "TXT",
        "name": f"_dmarc.{domain}",
        "content": get_dmarc_record(),
    })
    verify_fqdn = f"{VERIFY_RECORD['name']}.{domain}"
    records.append({
        "id": _new_id("rec"),
        "type": "TXT",
        "name": verify_fqdn,
        "content": VERIFY_RECORD["value"],
    })
    return records


_state = _seed_state()


def reset_demo_state():
    """Restore seeded in-memory demo API state."""
    global _state
    with _lock:
        _state = _seed_state()


def _domain_state(domain):
    domain = domain.lower().strip()
    return _state["domains"].get(domain)


def _require_domain(domain):
    state = _domain_state(domain)
    if not state:
        return None, ({"success": False, "error": {"message": "Domain not found"}}, 404)
    return state, None


def _success(data=None, status=200):
    payload = {"success": True}
    if data is not None:
        payload["data"] = data
    return payload, status


def _error(message, status=400):
    return {"success": False, "error": {"message": message}}, status


def _dns_payload(domain):
    data = copy.deepcopy(MX_DNS_TEMPLATE)
    _, fqdn = _dkim_parts(data["dkim"], domain)
    data["dkim"]["name"] = fqdn.replace(f".{domain}", "") if fqdn.endswith(f".{domain}") else data["dkim"]["name"]
    data["dmarc"] = {"name": "_dmarc", "value": get_dmarc_record()}
    return data


def _mark_dns_deployed(domain):
    state = _domain_state(domain)
    if not state:
        return
    state["dns_deployed"] = True
    if not state.get("cf_zone_id"):
        zone_id = _new_id("zone")
        state["cf_zone_id"] = zone_id
        _state["cf_zones"][zone_id] = {
            "name": domain,
            "records": _demo_mail_records(domain),
        }


def demo_mx_request_raw(method, path, payload=None):
    path_only = path.split("?", 1)[0].rstrip("/") or "/"
    parts = [part for part in path_only.split("/") if part]

    with _lock:
        if parts == ["domains"] and method == "GET":
            return _success(sorted(_state["domains"].keys()))

        if parts == ["domains"] and method == "POST":
            domain = (payload or {}).get("domain", "").lower().strip()
            if not is_demo_domain(domain):
                return _error("Demo mode only supports example.com, notarealsite.org, and demo.net")
            if domain in _state["domains"]:
                return _error("Domain already exists")
            _state["domains"][domain] = _empty_domain()
            return _success(status=201)

        if parts == ["verification-key"] and method == "GET":
            return _success({"record": copy.deepcopy(VERIFY_RECORD)})

        if parts == ["quota"] and method == "GET":
            used = 12 * (1024 ** 3)
            limit = 50 * (1024 ** 3)
            return _success({
                "total_limit": limit,
                "total_used": used,
                "percent_used": round((used / limit) * 100, 1),
                "grace_period": None,
            })

        if parts == ["quota", "email"] and method == "GET":
            return _success({"accounts": [], "total_used": 0})

        if len(parts) == 2 and parts[0] == "domains":
            domain = parts[1]
            if method == "GET":
                state, err = _require_domain(domain)
                if err:
                    return err
                return _success({"domain": domain, "mail_hosting": state["mail_hosting"]})
            if method == "DELETE":
                if not is_demo_domain(domain):
                    return _error("Only demo domains can be removed in demo mode")
                if domain not in _state["domains"]:
                    return _error("Domain not found", 404)
                zone_id = _state["domains"][domain].get("cf_zone_id")
                del _state["domains"][domain]
                if zone_id:
                    _state["cf_zones"].pop(zone_id, None)
                return _success()

        if len(parts) == 3 and parts[0] == "domains" and parts[2] == "mail-status" and method == "PATCH":
            state, err = _require_domain(parts[1])
            if err:
                return err
            enabled = None
            if isinstance(payload, dict):
                if "enabled" in payload:
                    enabled = payload["enabled"]
                elif "mail_hosting" in payload:
                    enabled = payload["mail_hosting"]
            if enabled is None:
                return _error("Missing mail hosting state")
            state["mail_hosting"] = bool(enabled)
            return _success()

        if len(parts) == 3 and parts[0] == "domains" and parts[2] == "dns" and method == "GET":
            state, err = _require_domain(parts[1])
            if err:
                return err
            return _success(_dns_payload(parts[1]))

        if len(parts) == 3 and parts[0] == "domains" and parts[2] == "email-accounts":
            domain = parts[1]
            state, err = _require_domain(domain)
            if err:
                return err
            if method == "GET":
                accounts = list(state["email_accounts"].values())
                return _success(accounts)
            if method == "POST":
                username = (payload or {}).get("username", "").lower().strip()
                if not username:
                    return _error("Invalid mailbox username")
                if username in state["email_accounts"]:
                    return _error("Mailbox already exists")
                state["email_accounts"][username] = _mailbox(
                    username,
                    quota=(payload or {}).get("quota", 1024),
                    limit=(payload or {}).get("limit", 500),
                )
                return _success(status=201)

        if len(parts) == 4 and parts[0] == "domains" and parts[2] == "email-accounts":
            domain, username = parts[1], parts[3].lower()
            state, err = _require_domain(domain)
            if err:
                return err
            account = state["email_accounts"].get(username)
            if method == "GET":
                if not account:
                    return _error("Mailbox not found", 404)
                return _success(account)
            if method == "PATCH":
                if not account:
                    return _error("Mailbox not found", 404)
                if isinstance(payload, dict):
                    if "quota" in payload:
                        account["quota"] = int(payload["quota"])
                    if "limit" in payload:
                        account["limit"] = int(payload["limit"])
                    if "password" in payload:
                        pass  # ponytail: demo accepts password changes without storing secrets
                return _success()
            if method == "DELETE":
                if username not in state["email_accounts"]:
                    return _error("Mailbox not found", 404)
                del state["email_accounts"][username]
                return _success()

        if len(parts) == 3 and parts[0] == "domains" and parts[2] == "forwarders":
            domain = parts[1]
            state, err = _require_domain(domain)
            if err:
                return err
            if method == "GET":
                return _success(list(state["forwarders"].values()))
            if method == "POST":
                alias = (payload or {}).get("alias", "").lower().strip()
                destinations = (payload or {}).get("destinations") or []
                if not alias or not destinations:
                    return _error("Alias and destinations are required")
                state["forwarders"][alias] = {"alias": alias, "destinations": list(destinations)}
                return _success(status=201)

        if len(parts) == 4 and parts[0] == "domains" and parts[2] == "forwarders" and method == "DELETE":
            domain, alias = parts[1], parts[3].lower()
            state, err = _require_domain(domain)
            if err:
                return err
            if alias not in state["forwarders"]:
                return _error("Forwarder not found", 404)
            del state["forwarders"][alias]
            return _success()

        if len(parts) == 3 and parts[0] == "domains" and parts[2] == "catch-all":
            domain = parts[1]
            state, err = _require_domain(domain)
            if err:
                return err
            if method == "GET":
                return _success(copy.deepcopy(state["catch_all"]))
            if method == "PATCH":
                catch_type = (payload or {}).get("type", "fail")
                address = (payload or {}).get("address")
                state["catch_all"] = {
                    "type": catch_type,
                    "address": address if catch_type == "address" else None,
                }
                return _success()

        if len(parts) == 3 and parts[0] == "domains" and parts[2] == "pointers":
            domain = parts[1]
            state, err = _require_domain(domain)
            if err:
                return err
            if method == "GET":
                return _success(copy.deepcopy(state["pointers"]))
            if method == "POST":
                pointer = (payload or {}).get("pointer", "").lower().strip()
                if not pointer:
                    return _error("Pointer domain is required")
                entry_type = "alias" if (payload or {}).get("alias") else "domain"
                state["pointers"].append({"pointer": pointer, "type": entry_type})
                return _success(status=201)

        if len(parts) == 4 and parts[0] == "domains" and parts[2] == "pointers" and method == "DELETE":
            domain, pointer = parts[1], parts[3].lower()
            state, err = _require_domain(domain)
            if err:
                return err
            before = len(state["pointers"])
            state["pointers"] = [item for item in state["pointers"] if item["pointer"] != pointer]
            if len(state["pointers"]) == before:
                return _error("Pointer not found", 404)
            return _success()

        if len(parts) >= 4 and parts[0] == "domains" and parts[2] == "spam":
            domain = parts[1]
            state, err = _require_domain(domain)
            if err:
                return err
            spam = state["spam"]
            resource = parts[3]

            if resource == "settings":
                if method == "GET":
                    return _success({"high_score": spam["high_score"]})
                if method == "PATCH":
                    if "high_score" in (payload or {}):
                        spam["high_score"] = int(payload["high_score"])
                    return _success()

            if resource == "whitelist":
                if method == "GET":
                    return _success(list(spam["whitelist"]))
                if method == "POST":
                    entry = (payload or {}).get("entry", "").strip()
                    if not entry:
                        return _error("Entry is required")
                    if entry not in spam["whitelist"]:
                        spam["whitelist"].append(entry)
                    return _success(status=201)
                if method == "DELETE" and len(parts) == 5:
                    entry = parts[4]
                    if entry not in spam["whitelist"]:
                        return _error("Entry not found", 404)
                    spam["whitelist"].remove(entry)
                    return _success()

            if resource == "blacklist":
                if method == "GET":
                    return _success(list(spam["blacklist"]))
                if method == "POST":
                    entry = (payload or {}).get("entry", "").strip()
                    if not entry:
                        return _error("Entry is required")
                    if entry not in spam["blacklist"]:
                        spam["blacklist"].append(entry)
                    return _success(status=201)
                if method == "DELETE" and len(parts) == 5:
                    entry = parts[4]
                    if entry not in spam["blacklist"]:
                        return _error("Entry not found", 404)
                    spam["blacklist"].remove(entry)
                    return _success()

    return _error(f"Demo backend does not implement {method} {path}", 501)


def demo_cf_request(method, path, payload=None):
    with _lock:
        if method == "GET" and path.startswith("/zones?name="):
            domain = path.split("=", 1)[1].lower().strip()
            for zone_id, zone in _state["cf_zones"].items():
                if zone["name"] == domain:
                    return {"success": True, "result": [{"id": zone_id, "name": domain}]}
            return {"success": True, "result": []}

        if method == "POST" and path == "/zones":
            domain = (payload or {}).get("name", "").lower().strip()
            if not is_demo_domain(domain):
                return {"success": False, "errors": [{"message": "Demo mode only supports fictional demo domains"}]}
            existing = _domain_state(domain)
            zone_id = existing.get("cf_zone_id") if existing else None
            if not zone_id:
                zone_id = _new_id("zone")
            _state["cf_zones"][zone_id] = {"name": domain, "records": []}
            if existing:
                existing["cf_zone_id"] = zone_id
            return {"success": True, "result": {"id": zone_id, "name": domain}}

        zone_match = re.match(r"^/zones/([^/]+)/dns_records(?:\?.*)?$", path)
        if method == "GET" and zone_match:
            zone_id = zone_match.group(1)
            zone = _state["cf_zones"].get(zone_id, {"records": []})
            return {"success": True, "result": copy.deepcopy(zone["records"])}

        create_match = re.match(r"^/zones/([^/]+)/dns_records$", path)
        if method == "POST" and create_match:
            zone_id = create_match.group(1)
            zone = _state["cf_zones"].setdefault(zone_id, {"name": "", "records": []})
            record = copy.deepcopy(payload or {})
            record["id"] = _new_id("rec")
            zone["records"].append(record)
            domain = zone.get("name") or ""
            if domain:
                _mark_dns_deployed(domain)
            return {"success": True, "result": record}

        update_match = re.match(r"^/zones/([^/]+)/dns_records/([^/]+)$", path)
        if update_match:
            zone_id, record_id = update_match.groups()
            zone = _state["cf_zones"].get(zone_id)
            if not zone:
                return {"success": False, "errors": [{"message": "Zone not found"}]}
            if method == "PUT":
                for idx, record in enumerate(zone["records"]):
                    if record["id"] == record_id:
                        updated = {**record, **(payload or {})}
                        updated["id"] = record_id
                        zone["records"][idx] = updated
                        if zone.get("name"):
                            _mark_dns_deployed(zone["name"])
                        return {"success": True, "result": updated}
                return {"success": False, "errors": [{"message": "Record not found"}]}
            if method == "DELETE":
                before = len(zone["records"])
                zone["records"] = [rec for rec in zone["records"] if rec["id"] != record_id]
                if len(zone["records"]) == before:
                    return {"success": False, "errors": [{"message": "Record not found"}]}
                return {"success": True, "result": {"id": record_id}}

    return {"success": False, "errors": [{"message": f"Demo Cloudflare backend does not implement {method} {path}"}]}


def demo_npm_request(method, path, json_payload=None, files=None):
    with _lock:
        if method == "GET" and path == "/nginx/proxy-hosts":
            return copy.deepcopy(_state["npm_proxy_hosts"])
        if method == "GET" and path == "/nginx/certificates":
            return copy.deepcopy(_state["npm_certificates"])

        if method == "POST" and path == "/nginx/proxy-hosts":
            host = dict(json_payload or {})
            host["id"] = int(uuid.uuid4().int % 1_000_000)
            host.setdefault("enabled", True)
            _state["npm_proxy_hosts"].append(host)
            return host

        update_host = re.match(r"^/nginx/proxy-hosts/(\d+)$", path)
        if method == "PUT" and update_host:
            host_id = int(update_host.group(1))
            for idx, host in enumerate(_state["npm_proxy_hosts"]):
                if host.get("id") == host_id:
                    updated = {**host, **(json_payload or {})}
                    updated["id"] = host_id
                    _state["npm_proxy_hosts"][idx] = updated
                    return updated
            return {}

        enable_host = re.match(r"^/nginx/proxy-hosts/(\d+)/enable$", path)
        if method == "POST" and enable_host:
            return {}

        if method == "POST" and path == "/nginx/certificates":
            cert = dict(json_payload or {})
            cert["id"] = int(uuid.uuid4().int % 1_000_000)
            _state["npm_certificates"].append(cert)
            return cert

        upload_cert = re.match(r"^/nginx/certificates/(\d+)/upload$", path)
        if method == "POST" and upload_cert:
            return {}

        delete_host = re.match(r"^/nginx/proxy-hosts/(\d+)$", path)
        if method == "DELETE" and delete_host:
            host_id = int(delete_host.group(1))
            _state["npm_proxy_hosts"] = [host for host in _state["npm_proxy_hosts"] if host.get("id") != host_id]
            return {}

        delete_cert = re.match(r"^/nginx/certificates/(\d+)$", path)
        if method == "DELETE" and delete_cert:
            cert_id = int(delete_cert.group(1))
            _state["npm_certificates"] = [cert for cert in _state["npm_certificates"] if cert.get("id") != cert_id]
            return {}

    raise ValueError(f"Demo NPM backend does not implement {method} {path}")


def demo_check_dns_health(domain, expected_dns, verification_record=None, dmarc_expected=None):
    domain = domain.lower().strip()
    state = _domain_state(domain) or {}
    deployed = bool(state.get("dns_deployed"))
    expected_dns = expected_dns or _dns_payload(domain)
    dmarc_expected = dmarc_expected or get_dmarc_record()

    def _pass_check(label, expected, found=None, message=None):
        return {
            "status": "pass" if deployed else "fail",
            "label": label,
            "expected": expected,
            "found": found if found is not None else ([expected] if deployed else []),
            "message": message or ("Record present (demo)" if deployed else "Record missing (demo — run DNS setup)"),
        }

    checks = {}
    expected_mx = expected_dns.get("mx_records") or []
    checks["mx"] = _pass_check("MX Records", expected_mx)

    spf_value = (expected_dns.get("spf") or {}).get("value", "")
    checks["spf"] = _pass_check("SPF (TXT)", spf_value)

    dkim_data = expected_dns.get("dkim") or {}
    _, dkim_fqdn = _dkim_parts(dkim_data, domain)
    checks["dkim"] = {
        **_pass_check("DKIM (TXT)", dkim_data.get("value", "")),
        "expected_host": dkim_fqdn,
    }

    checks["dmarc"] = {
        **_pass_check("DMARC (TXT)", dmarc_expected),
        "expected_host": f"_dmarc.{domain}",
    }

    if verification_record:
        verify_name = str(verification_record.get("name", "")).strip()
        verify_value = str(verification_record.get("value", "")).strip()
        verify_fqdn = f"{verify_name}.{domain}".lower() if verify_name else domain
        checks["verification"] = {
            **_pass_check("Domain Verification (TXT)", verify_value),
            "expected_host": verify_fqdn,
        }

    overall = overall_from_checks(checks) if deployed else "unhealthy"
    return {"domain": domain, "overall": overall, "checks": checks}
