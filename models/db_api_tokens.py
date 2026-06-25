"""API tokens for automation (Bearer auth, delegation-style scopes)."""

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone

from models.db_conn import get_conn
from models.db_delegations import _normalize_permissions, get_or_create_secret_key


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hash_token(raw_token):
    pepper = get_or_create_secret_key().encode("utf-8")
    return hmac.new(pepper, raw_token.encode("utf-8"), hashlib.sha256).hexdigest()


def _row_to_token(row):
    if not row:
        return None
    grants = []
    try:
        parsed = json.loads(row[5] or "[]")
        if isinstance(parsed, list):
            grants = parsed
    except (TypeError, json.JSONDecodeError):
        grants = []
    return {
        "id": row[0],
        "label": row[1],
        "token_prefix": row[2],
        "is_admin": bool(row[4]),
        "grants": grants,
        "created_at": row[6],
        "last_used_at": row[7],
        "revoked_at": row[8],
    }


def _grants_to_domain_grants(grants):
    domain_grants = {}
    delegated_domains = []
    for grant in grants or []:
        if not isinstance(grant, dict):
            continue
        domain = str(grant.get("domain") or "").strip().lower()
        if not domain:
            continue
        permissions = _normalize_permissions(grant.get("permissions"))
        domain_grants[domain] = permissions
        delegated_domains.append(domain)
    return domain_grants, delegated_domains


def build_user_from_api_token(record):
    """Session-shaped user dict for permission checks."""
    domain_grants, delegated_domains = _grants_to_domain_grants(record.get("grants"))
    label = str(record.get("label") or "api-token")
    return {
        "email": f"token:{label}",
        "is_admin": bool(record.get("is_admin")),
        "delegated_domains": delegated_domains,
        "domain_grants": domain_grants,
        "auth_via": "api_token",
        "token_id": record.get("id"),
    }


def list_api_tokens(*, include_revoked=False):
    query = """
        SELECT id, label, token_prefix, token_hash, is_admin, grants_json,
               created_at, last_used_at, revoked_at
        FROM api_tokens
    """
    if not include_revoked:
        query += " WHERE revoked_at IS NULL"
    query += " ORDER BY created_at DESC, id DESC"
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
    return [_row_to_token(row) for row in rows]


def create_api_token(*, label, is_admin=False, grants=None):
    label = str(label or "").strip()
    if not label:
        raise ValueError("Token label is required")
    if len(label) > 80:
        raise ValueError("Token label is too long")

    normalized_grants = []
    if not is_admin:
        for grant in grants or []:
            if not isinstance(grant, dict):
                continue
            domain = str(grant.get("domain") or "").strip().lower()
            if not domain:
                continue
            permissions = _normalize_permissions(grant.get("permissions"))
            if not permissions:
                raise ValueError(f"Select at least one permission for {domain}")
            normalized_grants.append({"domain": domain, "permissions": permissions})
        if not normalized_grants:
            raise ValueError(
                "Select at least one domain with permissions, or grant admin access."
            )

    raw_token = f"mxm_{secrets.token_urlsafe(32)}"
    token_hash = _hash_token(raw_token)
    token_prefix = raw_token[:12]
    created_at = _utc_now()
    grants_json = json.dumps(normalized_grants, ensure_ascii=False)

    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO api_tokens
                (label, token_prefix, token_hash, is_admin, grants_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                label,
                token_prefix,
                token_hash,
                1 if is_admin else 0,
                grants_json,
                created_at,
            ),
        )
        token_id = cursor.lastrowid
        conn.commit()

    record = {
        "id": token_id,
        "label": label,
        "token_prefix": token_prefix,
        "is_admin": bool(is_admin),
        "grants": normalized_grants,
        "created_at": created_at,
        "last_used_at": None,
        "revoked_at": None,
    }
    return record, raw_token


def lookup_api_token(raw_token):
    if not raw_token or not str(raw_token).startswith("mxm_"):
        return None
    token_hash = _hash_token(str(raw_token).strip())
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, label, token_prefix, token_hash, is_admin, grants_json,
                   created_at, last_used_at, revoked_at
            FROM api_tokens
            WHERE token_hash = ? AND revoked_at IS NULL
            """,
            (token_hash,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        cursor.execute(
            "UPDATE api_tokens SET last_used_at = ? WHERE id = ?",
            (_utc_now(), row[0]),
        )
        conn.commit()
    return _row_to_token(row)


def revoke_api_token(token_id):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE api_tokens SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (_utc_now(), int(token_id)),
        )
        conn.commit()
        return cursor.rowcount > 0
