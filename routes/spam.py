from flask import Blueprint, request

from utils.auth_helpers import require_permission
from services.mxroute import audited_mx_domain, mx_domain_request

spam_bp = Blueprint("spam", __name__)


@spam_bp.route("/api/domains/<domain>/spam/settings", methods=["GET"])
@require_permission("spam")
def get_spam_settings(domain):
    return mx_domain_request("GET", domain, "/spam/settings")


@spam_bp.route("/api/domains/<domain>/spam/settings", methods=["PATCH"])
@require_permission("spam")
def update_spam_settings(domain):
    return audited_mx_domain(
        "PATCH",
        domain,
        "/spam/settings",
        request.json,
        "spam.settings_update",
    )


@spam_bp.route("/api/domains/<domain>/spam/whitelist", methods=["GET"])
@require_permission("spam")
def get_spam_whitelist(domain):
    return mx_domain_request("GET", domain, "/spam/whitelist")


@spam_bp.route("/api/domains/<domain>/spam/whitelist", methods=["POST"])
@require_permission("spam")
def create_spam_whitelist(domain):
    data = request.json or {}
    entry = data.get("entry", "")
    return audited_mx_domain(
        "POST",
        domain,
        "/spam/whitelist",
        request.json,
        "spam.whitelist_add",
        target=f"{entry}@{domain}" if entry else domain,
    )


@spam_bp.route("/api/domains/<domain>/spam/whitelist/<path:entry>", methods=["DELETE"])
@require_permission("spam")
def delete_spam_whitelist(domain, entry):
    return audited_mx_domain(
        "DELETE",
        domain,
        f"/spam/whitelist/{entry}",
        None,
        "spam.whitelist_remove",
        target=f"{entry}@{domain}",
    )


@spam_bp.route("/api/domains/<domain>/spam/blacklist", methods=["GET"])
@require_permission("spam")
def get_spam_blacklist(domain):
    return mx_domain_request("GET", domain, "/spam/blacklist")


@spam_bp.route("/api/domains/<domain>/spam/blacklist", methods=["POST"])
@require_permission("spam")
def create_spam_blacklist(domain):
    data = request.json or {}
    entry = data.get("entry", "")
    return audited_mx_domain(
        "POST",
        domain,
        "/spam/blacklist",
        request.json,
        "spam.blacklist_add",
        target=f"{entry}@{domain}" if entry else domain,
    )


@spam_bp.route("/api/domains/<domain>/spam/blacklist/<path:entry>", methods=["DELETE"])
@require_permission("spam")
def delete_spam_blacklist(domain, entry):
    return audited_mx_domain(
        "DELETE",
        domain,
        f"/spam/blacklist/{entry}",
        None,
        "spam.blacklist_remove",
        target=f"{entry}@{domain}",
    )
