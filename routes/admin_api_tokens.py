from functools import wraps

from flask import jsonify, request

from models.db_api_tokens import create_api_token, list_api_tokens, revoke_api_token
from routes.admin_blueprint import admin_bp
from routes.admin_delegations import parse_delegation_grants, _is_admin_from_domains
from services.mxroute import audit
from utils.auth_helpers import is_api_token_auth, require_admin


def _require_browser_admin(f):
    """Admin session only — API tokens cannot create or revoke other tokens."""

    @wraps(f)
    @require_admin
    def wrapped(*args, **kwargs):
        if is_api_token_auth():
            return jsonify(
                {
                    "success": False,
                    "error": {"message": "API tokens cannot manage other API tokens."},
                }
            ), 403
        return f(*args, **kwargs)

    return wrapped


def _public_token_row(record):
    return {
        "id": record["id"],
        "label": record["label"],
        "token_prefix": record["token_prefix"],
        "is_admin": bool(record.get("is_admin")),
        "grants": record.get("grants") or [],
        "created_at": record.get("created_at"),
        "last_used_at": record.get("last_used_at"),
    }


@admin_bp.route("/api/admin/api-tokens", methods=["GET"])
@_require_browser_admin
def get_api_tokens():
    tokens = [_public_token_row(row) for row in list_api_tokens()]
    return jsonify({"success": True, "data": tokens})


@admin_bp.route("/api/admin/api-tokens", methods=["POST"])
@_require_browser_admin
def post_api_token():
    data = request.json or {}
    label = str(data.get("label") or "").strip()
    is_admin = bool(data.get("is_admin")) or _is_admin_from_domains(data)
    grants = parse_delegation_grants(data)
    try:
        record, raw_token = create_api_token(
            label=label,
            is_admin=is_admin,
            grants=grants,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": {"message": str(exc)}}), 400

    audit(
        "api_token.create",
        target=label,
        token_id=record["id"],
        is_admin=is_admin,
        grant_count=len(record.get("grants") or []),
    )
    payload = _public_token_row(record)
    payload["token"] = raw_token
    return jsonify({"success": True, "data": payload}), 201


@admin_bp.route("/api/admin/api-tokens/<int:token_id>", methods=["DELETE"])
@_require_browser_admin
def delete_api_token(token_id):
    if revoke_api_token(token_id):
        audit("api_token.revoke", target=str(token_id))
        return jsonify({"success": True})
    return jsonify(
        {
            "success": False,
            "error": {"message": "API token not found or already revoked."},
        }
    ), 404
