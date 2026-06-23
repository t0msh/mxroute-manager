import os
import requests
from flask import jsonify

from models.db import get_config_value, get_dmarc_record
from utils.auth_helpers import get_current_user
from utils.audit_log import write_audit_log
from utils.validators import nested_dict_get

BASE_URL = os.getenv("MXROUTE_API_URL", "https://api.mxroute.com").rstrip("/")


def get_mx_headers():
    return {
        "X-Server": get_config_value("MX_SERVER"),
        "X-Username": get_config_value("MX_USER"),
        "X-API-Key": get_config_value("MX_API_KEY"),
        "Content-Type": "application/json",
    }


def mx_request_raw(method, path, payload=None):
    if method not in ("GET", "POST", "PATCH", "DELETE"):
        return {"success": False, "error": {"message": "Invalid method"}}, 400
    url = f"{BASE_URL}{path}"
    headers = get_mx_headers()
    try:
        response = requests.request(
            method, url, json=payload, headers=headers, timeout=30
        )

        if response.status_code == 204 or (not response.text.strip()):
            return {"success": True}, response.status_code

        try:
            return response.json(), response.status_code
        except ValueError:
            return {
                "success": False,
                "error": {"message": response.text},
            }, response.status_code

    except requests.exceptions.RequestException as e:
        return {"success": False, "error": {"message": str(e)}}, 500


def mx_request(method, path, payload=None):
    res, status = mx_request_raw(method, path, payload)
    return jsonify(res), status


def audit(action, target="", **details):
    try:
        user = get_current_user()
    except RuntimeError:
        user = None
    email = (user or {}).get("email", "system")
    write_audit_log(action, email, target, details or None)


def audited_mx(method, path, payload, action, target=""):
    res, status = mx_request_raw(method, path, payload)
    if status in (200, 201, 204) and (
        not isinstance(res, dict) or res.get("success", True)
    ):
        details = {}
        if isinstance(payload, dict):
            details = {
                key: value
                for key, value in payload.items()
                if "password" not in key.lower()
            }
        audit(action, target=target or path, **details)
    return jsonify(res), status


def domain_on_mxroute(domain):
    domains_list_res, domains_status = mx_request_raw("GET", "/domains")
    if domains_status != 200:
        return False
    domain_lower = domain.lower()
    return any(d.lower() == domain_lower for d in domains_list_res.get("data", []))


def get_mxroute_verification_record():
    verify_res, verify_status = mx_request_raw("GET", "/verification-key")
    if verify_status != 200:
        return None
    return nested_dict_get(verify_res, "data", "record")


def inject_dmarc(data):
    """Attach the configured DMARC expectation to an MXroute DNS data dict."""
    data = data or {}
    data["dmarc"] = {"name": "_dmarc", "value": get_dmarc_record()}
    return data


def get_mxroute_dns_data(domain):
    mx_dns_res, mx_dns_status = mx_request_raw("GET", f"/domains/{domain}/dns")
    if mx_dns_status != 200:
        return None
    return inject_dmarc(mx_dns_res.get("data"))


def get_domain_mail_hosting(domain):
    res, status = mx_request_raw("GET", f"/domains/{domain}")
    if status != 200:
        return True
    return bool(nested_dict_get(res, "data", "mail_hosting", default=True))


def register_domain_on_mxroute(domain, steps=None):
    if domain_on_mxroute(domain):
        if steps is not None:
            steps.append("Domain already registered on MXroute")
        return "skipped"
    mx_domain_add, mx_add_status = mx_request_raw(
        "POST", "/domains", {"domain": domain}
    )
    if mx_add_status not in [200, 201]:
        err_msg = nested_dict_get(
            mx_domain_add, "error", "message", default="Unknown error"
        )
        raise ValueError(f"Failed to register domain with MXroute: {err_msg}")
    if steps is not None:
        steps.append("Domain registered on MXroute successfully")
    audit("domain.create", target=domain)
    return "added"
