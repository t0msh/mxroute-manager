from flask import Blueprint, request

from utils.auth_helpers import require_permission
from services.mxroute import mx_request, audited_mx

spam_bp = Blueprint("spam", __name__)


@spam_bp.route("/api/domains/<domain>/spam/settings", methods=["GET"])
@require_permission("spam")
def get_spam_settings(domain):
    return mx_request("GET", f"/domains/{domain}/spam/settings")


@spam_bp.route("/api/domains/<domain>/spam/settings", methods=["PATCH"])
@require_permission("spam")
def update_spam_settings(domain):
    return audited_mx(
        "PATCH",
        f"/domains/{domain}/spam/settings",
        request.json,
        "spam.settings_update",
        target=domain,
    )


@spam_bp.route("/api/domains/<domain>/spam/whitelist", methods=["GET"])
@require_permission("spam")
def get_spam_whitelist(domain):
    return mx_request("GET", f"/domains/{domain}/spam/whitelist")


@spam_bp.route("/api/domains/<domain>/spam/whitelist", methods=["POST"])
@require_permission("spam")
def create_spam_whitelist(domain):
    data = request.json or {}
    entry = data.get("entry", "")
    return audited_mx(
        "POST",
        f"/domains/{domain}/spam/whitelist",
        request.json,
        "spam.whitelist_add",
        target=f"{entry}@{domain}" if entry else domain,
    )


@spam_bp.route("/api/domains/<domain>/spam/whitelist/<path:entry>", methods=["DELETE"])
@require_permission("spam")
def delete_spam_whitelist(domain, entry):
    return audited_mx(
        "DELETE",
        f"/domains/{domain}/spam/whitelist/{entry}",
        None,
        "spam.whitelist_remove",
        target=f"{entry}@{domain}",
    )


@spam_bp.route("/api/domains/<domain>/spam/blacklist", methods=["GET"])
@require_permission("spam")
def get_spam_blacklist(domain):
    return mx_request("GET", f"/domains/{domain}/spam/blacklist")


@spam_bp.route("/api/domains/<domain>/spam/blacklist", methods=["POST"])
@require_permission("spam")
def create_spam_blacklist(domain):
    data = request.json or {}
    entry = data.get("entry", "")
    return audited_mx(
        "POST",
        f"/domains/{domain}/spam/blacklist",
        request.json,
        "spam.blacklist_add",
        target=f"{entry}@{domain}" if entry else domain,
    )


@spam_bp.route("/api/domains/<domain>/spam/blacklist/<path:entry>", methods=["DELETE"])
@require_permission("spam")
def delete_spam_blacklist(domain, entry):
    return audited_mx(
        "DELETE",
        f"/domains/{domain}/spam/blacklist/{entry}",
        None,
        "spam.blacklist_remove",
        target=f"{entry}@{domain}",
    )
