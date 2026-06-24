"""CSV / bulk mailbox import validation."""

from services.mailbox_provision import DEFAULT_LIMIT, DEFAULT_QUOTA, MAX_IMPORT_ROWS
from utils.auth_helpers import has_permission, is_user_admin
from utils.validators import (
    validate_domain,
    validate_mailbox_password,
    validate_recovery_email,
    validate_username,
)

_USERNAME_KEYS = ("username", "user")
_EMAIL_KEYS = ("email", "mailbox", "address")


def _pick(row, keys):
    if not isinstance(row, dict):
        return ""
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _parse_int(value, default):
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_import_row(raw, *, default_domain=""):
    """Normalize a CSV row dict into import fields."""
    domain = (_pick(raw, ("domain",)) or default_domain or "").strip().lower()
    username = _pick(raw, _USERNAME_KEYS).lower()
    email_value = _pick(raw, _EMAIL_KEYS).lower()

    if not username and email_value and "@" in email_value:
        local, email_domain = email_value.split("@", 1)
        username = local.strip().lower()
        if not domain:
            domain = email_domain.strip().lower()
    elif not username and email_value:
        username = email_value

    password = _pick(raw, ("password", "pass"))
    recovery_email = _pick(raw, ("recovery_email", "recovery")).lower() or None
    quota = _parse_int(raw.get("quota"), DEFAULT_QUOTA)
    limit = _parse_int(raw.get("limit"), DEFAULT_LIMIT)

    line = raw.get("_line") or raw.get("line")
    try:
        line = int(line) if line is not None else None
    except (TypeError, ValueError):
        line = None

    return {
        "line": line,
        "domain": domain,
        "username": username,
        "password": password,
        "recovery_email": recovery_email,
        "quota": quota,
        "limit": limit,
    }


def validate_import_row(row, *, user, default_domain=""):
    """Validate one import row. Returns dict with ``valid``, ``errors``, and normalized fields."""
    normalized = normalize_import_row(row, default_domain=default_domain)
    errors = []
    domain = normalized["domain"]
    username = normalized["username"]
    password = normalized["password"]
    recovery_email = normalized["recovery_email"]
    quota = normalized["quota"]
    limit = normalized["limit"]

    if not domain:
        errors.append("Domain is required (column or active domain selector).")
    elif not validate_domain(domain):
        errors.append(f"Invalid domain: {domain}")
    elif user and not is_user_admin(user) and not has_permission(user, domain, "emails"):
        errors.append(f"No emails permission for {domain}")

    if not username:
        errors.append("Username is required.")
    elif not validate_username(username):
        errors.append(f"Invalid username: {username}")

    if password and not validate_mailbox_password(password):
        errors.append("Password does not meet requirements.")

    if quota is None:
        errors.append("Quota must be a number (MB).")
    elif quota < 0:
        errors.append("Quota cannot be negative.")

    if limit is None:
        errors.append("Daily send limit must be a number.")
    elif limit < 0:
        errors.append("Daily send limit cannot be negative.")

    if recovery_email:
        mailbox_email = f"{username}@{domain}" if username and domain else ""
        if mailbox_email:
            ok, message = validate_recovery_email(mailbox_email, recovery_email)
            if not ok:
                errors.append(message)

    needs_password = not password
    valid = not errors and not needs_password

    return {
        **normalized,
        "valid": valid,
        "needs_password": needs_password,
        "already_exists": False,
        "duplicate_in_csv": False,
        "errors": errors,
    }


def _normalize_existing_by_domain(data):
    if not isinstance(data, dict):
        return {}
    normalized = {}
    for domain, names in data.items():
        domain_key = str(domain or "").strip().lower()
        if not domain_key or not validate_domain(domain_key):
            continue
        if not isinstance(names, (list, tuple, set)):
            continue
        normalized[domain_key] = {
            str(name).strip().lower() for name in names if str(name).strip()
        }
    return normalized


def _apply_import_duplicate_checks(rows, existing_by_domain=None):
    seen_csv = set()
    existing_by_domain = _normalize_existing_by_domain(existing_by_domain)

    for row in rows:
        domain = row.get("domain") or ""
        username = row.get("username") or ""
        if not domain or not username:
            continue

        key = (domain, username)
        if key in seen_csv:
            if not row.get("errors"):
                row["duplicate_in_csv"] = True
                row["valid"] = False
                row["errors"] = list(row.get("errors") or []) + [
                    "Duplicate mailbox in this CSV."
                ]
            continue
        seen_csv.add(key)

        if row.get("errors"):
            continue

        existing = existing_by_domain.get(domain)
        if existing and username in existing:
            row["already_exists"] = True
            row["valid"] = False
            row["errors"] = list(row.get("errors") or []) + [
                "Mailbox already exists on this domain."
            ]


def preview_mailbox_import(rows, *, user, default_domain="", existing_by_domain=None):
    if not isinstance(rows, list):
        rows = []
    if len(rows) > MAX_IMPORT_ROWS:
        return {
            "ok": False,
            "status": 400,
            "message": f"Import limited to {MAX_IMPORT_ROWS} rows per batch.",
        }

    evaluated = [
        validate_import_row(row, user=user, default_domain=default_domain) for row in rows
    ]
    _apply_import_duplicate_checks(evaluated, existing_by_domain)
    valid_count = sum(1 for row in evaluated if row["valid"])
    needs_password_count = sum(
        1 for row in evaluated if row["needs_password"] and not row["errors"]
    )
    exists_count = sum(1 for row in evaluated if row.get("already_exists"))
    duplicate_csv_count = sum(1 for row in evaluated if row.get("duplicate_in_csv"))
    invalid_count = len(evaluated) - valid_count

    return {
        "ok": True,
        "status": 200,
        "data": {
            "rows": evaluated,
            "summary": {
                "total": len(evaluated),
                "valid": valid_count,
                "invalid": invalid_count,
                "needs_password": needs_password_count,
                "already_exists": exists_count,
                "duplicate_in_csv": duplicate_csv_count,
            },
        },
    }
