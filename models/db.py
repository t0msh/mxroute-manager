import os
import json
import sqlite3
import secrets
import hashlib
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger(__name__)

DATABASE_FILE = os.getenv(
    "DATABASE_FILE",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "mxroute-manager.db",
    ),
)
MAPPING_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "domain_mapping.json"
)

ALL_PERMISSIONS = ("dashboard", "emails", "forwarders", "spam", "dns")
DEFAULT_PERMISSIONS = list(ALL_PERMISSIONS)

ENV_ONLY_SECRET_KEYS = frozenset(
    {
        "MX_API_KEY",
        "CF_API_TOKEN",
        "CF_ORIGIN_CA_KEY",
        "OIDC_CLIENT_SECRET",
        "NPM_SECRET",
        "RESET_SMTP_PASSWORD",
    }
)
MASKED_SECRET_KEYS = ENV_ONLY_SECRET_KEYS | frozenset(
    {
        "ADMIN_PASSWORD",
        "SECRET_KEY",
    }
)
ADMIN_PASSWORD_HASH_KEY = "ADMIN_PASSWORD_HASH"
RESET_TOKEN_TTL_HOURS = 1
SETTINGS_UI_KEYS = [
    "OIDC_ENABLED",
    "OIDC_CLIENT_ID",
    "OIDC_DISCOVERY_URL",
    "OIDC_REDIRECT_URI",
    "OIDC_SCOPES",
    "OIDC_ADMIN_USERS",
    "OIDC_ADMIN_GROUP",
    "MX_SERVER",
    "MX_USER",
    "CF_ACCOUNT_ID",
    "ADMIN_USER",
    "MAILBOX_RESET_ENABLED",
    "RESET_SMTP_HOST",
    "RESET_SMTP_PORT",
    "RESET_SMTP_USER",
    "RESET_SMTP_FROM",
    "RESET_SMTP_USE_TLS",
]
SETTINGS_RESPONSE_KEYS = SETTINGS_UI_KEYS + sorted(MASKED_SECRET_KEYS)


def get_env_config(key, default=None):
    return os.getenv(key, default)


@contextmanager
def get_conn():
    """Yield a SQLite connection that is always closed, even on exceptions."""
    conn = sqlite3.connect(DATABASE_FILE)
    try:
        yield conn
    finally:
        conn.close()


# ponytail: single-process in-memory cache for DB-backed settings. Settings change
# only via admin action, so we clear the whole cache on any write. Ceiling: per-worker
# cache (no cross-process invalidation); upgrade path is a shared cache/pubsub if needed.
_MISSING = object()
_settings_cache = {}


def invalidate_settings_cache():
    _settings_cache.clear()


def get_config_value(key, default=None):
    if key in ENV_ONLY_SECRET_KEYS:
        return get_env_config(key, default)

    cached = _settings_cache.get(key, _MISSING)
    if cached is not _MISSING:
        return cached if cached is not None else get_env_config(key, default)

    stored = None
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
        if row is not None:
            stored = row[0]
        _settings_cache[key] = stored
    except Exception as e:
        logger.warning("Failed to read setting %s: %s", key, e)

    if stored is not None:
        return stored
    return get_env_config(key, default)


def get_admin_password_hash():
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value FROM settings WHERE key = ?", (ADMIN_PASSWORD_HASH_KEY,)
            )
            row = cursor.fetchone()
        if row and row[0]:
            return row[0]
    except Exception as e:
        logger.warning("Failed to read admin password hash: %s", e)
    return None


def verify_admin_password(password):
    password_hash = get_admin_password_hash()
    if not password_hash:
        return False
    return check_password_hash(password_hash, password)


def set_admin_password_hash(password, admin_email=None):
    password_hash = generate_password_hash(password)
    admin_email = (admin_email or get_admin_user()).lower().strip()
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (ADMIN_PASSWORD_HASH_KEY, password_hash),
        )
        cursor.execute("DELETE FROM settings WHERE key = ?", ("ADMIN_PASSWORD",))
        cursor.execute("SELECT id FROM users WHERE email = ?", (admin_email,))
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE users SET password_hash = ?, is_admin = 1 WHERE id = ?",
                (password_hash, row[0]),
            )
        else:
            cursor.execute(
                "INSERT INTO users (email, password_hash, is_admin) VALUES (?, ?, 1)",
                (admin_email, password_hash),
            )
        conn.commit()
    invalidate_settings_cache()


def _looks_like_password_hash(value):
    return isinstance(value, str) and (
        value.startswith("pbkdf2:") or value.startswith("scrypt:")
    )


def migrate_settings_secrets(cursor):
    for key in ENV_ONLY_SECRET_KEYS:
        # Keep legacy RESET_SMTP_PASSWORD in SQLite until .env is populated so
        # existing installs are not broken on upgrade.
        if key == "RESET_SMTP_PASSWORD" and not get_env_config("RESET_SMTP_PASSWORD"):
            continue
        cursor.execute("DELETE FROM settings WHERE key = ?", (key,))

    cursor.execute("SELECT value FROM settings WHERE key = ?", ("ADMIN_PASSWORD",))
    legacy_password_row = cursor.fetchone()
    cursor.execute(
        "SELECT value FROM settings WHERE key = ?", (ADMIN_PASSWORD_HASH_KEY,)
    )
    hash_row = cursor.fetchone()

    if (
        legacy_password_row
        and legacy_password_row[0]
        and not _looks_like_password_hash(legacy_password_row[0])
    ):
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (ADMIN_PASSWORD_HASH_KEY, generate_password_hash(legacy_password_row[0])),
        )
        cursor.execute("DELETE FROM settings WHERE key = ?", ("ADMIN_PASSWORD",))
    elif not hash_row or not hash_row[0]:
        env_password = get_env_config("ADMIN_PASSWORD")
        if env_password:
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (ADMIN_PASSWORD_HASH_KEY, generate_password_hash(env_password)),
            )
            cursor.execute("DELETE FROM settings WHERE key = ?", ("ADMIN_PASSWORD",))
    elif get_env_config("ADMIN_PASSWORD_FORCE_SYNC", "").lower() in (
        "true",
        "1",
        "yes",
    ):
        # ponytail: one-shot recovery when ADMIN_PASSWORD in .env was changed after the
        # hash was already stored. Remove the flag after a successful restart.
        env_password = get_env_config("ADMIN_PASSWORD")
        if env_password:
            password_hash = generate_password_hash(env_password)
            admin_email = get_admin_user().lower().strip()
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (ADMIN_PASSWORD_HASH_KEY, password_hash),
            )
            cursor.execute("DELETE FROM settings WHERE key = ?", ("ADMIN_PASSWORD",))
            cursor.execute("SELECT id FROM users WHERE email = ?", (admin_email,))
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    "UPDATE users SET password_hash = ?, is_admin = 1 WHERE id = ?",
                    (password_hash, row[0]),
                )
            else:
                cursor.execute(
                    "INSERT INTO users (email, password_hash, is_admin) VALUES (?, ?, 1)",
                    (admin_email, password_hash),
                )
    invalidate_settings_cache()


def is_secret_configured(key):
    if key == "ADMIN_PASSWORD":
        return bool(get_admin_password_hash())
    if key == "RESET_SMTP_PASSWORD":
        return bool(get_reset_smtp_password())
    if key in ENV_ONLY_SECRET_KEYS:
        return bool(get_env_config(key))
    if key == "SECRET_KEY":
        return bool(get_config_value("SECRET_KEY"))
    return False


def mask_settings_for_response():
    settings_dict = {}
    for key in SETTINGS_RESPONSE_KEYS:
        if key in MASKED_SECRET_KEYS:
            settings_dict[key] = ""
            settings_dict[f"{key}_configured"] = is_secret_configured(key)
        else:
            settings_dict[key] = get_config_value(key, "")
    return settings_dict


# Dynamic Configuration Getters
def is_oidc_enabled():
    return get_config_value("OIDC_ENABLED", "false").lower() == "true"


def get_oidc_client_id():
    return get_config_value("OIDC_CLIENT_ID")


def get_oidc_client_secret():
    return get_config_value("OIDC_CLIENT_SECRET")


def get_oidc_discovery_url():
    return get_config_value("OIDC_DISCOVERY_URL")


def get_oidc_redirect_uri():
    return get_config_value("OIDC_REDIRECT_URI")


def get_oidc_scopes():
    return get_config_value("OIDC_SCOPES", "openid email profile groups").strip()


def get_oidc_admin_users():
    admin_users_raw = get_config_value("OIDC_ADMIN_USERS", "")
    return set(
        email.strip().lower() for email in admin_users_raw.split(",") if email.strip()
    )


def get_oidc_admin_group():
    return get_config_value("OIDC_ADMIN_GROUP", "administrators").strip()


def get_admin_user():
    return get_config_value("ADMIN_USER", "admin").strip().lower()


def admin_password_configured():
    return bool(get_admin_password_hash())


def get_dmarc_record():
    default = os.getenv("DMARC_RECORD", "v=DMARC1; p=none; sp=none; adkim=r; aspf=r;")
    return get_config_value("DMARC_RECORD", default).strip()


def use_secure_cookies():
    explicit = os.getenv("FORCE_HTTPS")
    if explicit is not None and explicit.strip() != "":
        return explicit.lower() in ("true", "1", "yes")
    return is_oidc_enabled()


def is_mailbox_reset_enabled():
    return get_config_value("MAILBOX_RESET_ENABLED", "false").lower() in (
        "true",
        "1",
        "yes",
    )


def get_reset_smtp_host():
    return (get_config_value("RESET_SMTP_HOST") or "").strip()


def get_reset_smtp_port():
    raw = get_config_value("RESET_SMTP_PORT", "587")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 587


def get_reset_smtp_user():
    return (get_config_value("RESET_SMTP_USER") or "").strip()


def _get_legacy_reset_smtp_password():
    """Read SMTP password saved before env-only migration (not written anymore)."""
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value FROM settings WHERE key = ?", ("RESET_SMTP_PASSWORD",)
            )
            row = cursor.fetchone()
        if row and row[0]:
            return row[0]
    except Exception as e:
        logger.warning("Failed to read legacy RESET_SMTP_PASSWORD from settings: %s", e)
    return None


def get_reset_smtp_password():
    env_password = get_env_config("RESET_SMTP_PASSWORD")
    if env_password:
        return env_password
    # ponytail: legacy DB fallback until RESET_SMTP_PASSWORD is set in .env.
    # migrate_settings_secrets keeps the DB row while env is unset.
    return _get_legacy_reset_smtp_password()


def get_reset_smtp_from():
    return (get_config_value("RESET_SMTP_FROM") or "").strip()


def reset_smtp_use_tls():
    return get_config_value("RESET_SMTP_USE_TLS", "true").lower() in (
        "true",
        "1",
        "yes",
    )


NOTIFICATION_SETTINGS_KEY = "NOTIFICATION_SETTINGS"


def _default_notification_settings():
    return {"enabled": False, "targets": [], "actions": []}


def get_notification_settings():
    raw = get_config_value(NOTIFICATION_SETTINGS_KEY, "")
    if not raw:
        return _default_notification_settings()
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        logger.warning("Invalid notification settings JSON; using defaults")
        return _default_notification_settings()
    if not isinstance(data, dict):
        return _default_notification_settings()
    return {
        "enabled": bool(data.get("enabled")),
        "targets": data.get("targets") if isinstance(data.get("targets"), list) else [],
        "actions": data.get("actions") if isinstance(data.get("actions"), list) else [],
    }


def save_notification_settings(config):
    if not isinstance(config, dict):
        raise ValueError("Notification settings must be an object")
    normalized = {
        "enabled": bool(config.get("enabled")),
        "targets": config.get("targets")
        if isinstance(config.get("targets"), list)
        else [],
        "actions": config.get("actions")
        if isinstance(config.get("actions"), list)
        else [],
    }
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (NOTIFICATION_SETTINGS_KEY, json.dumps(normalized, ensure_ascii=False)),
        )
        conn.commit()
    invalidate_settings_cache()
    return normalized


def _utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hash_reset_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def parse_mailbox_email(address):
    """Return (username, domain) for a full mailbox address, or (None, None)."""
    from utils.validators import validate_domain, validate_username, is_email_identifier

    if not address or not isinstance(address, str):
        return None, None
    address = address.strip().lower()
    if not is_email_identifier(address) or "@" not in address:
        return None, None
    username, domain = address.rsplit("@", 1)
    if not validate_username(username) or not validate_domain(domain):
        return None, None
    return username, domain


def get_recovery_email(mailbox_email):
    mailbox_email = (mailbox_email or "").strip().lower()
    if not mailbox_email:
        return None
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT recovery_email FROM mailbox_recovery WHERE mailbox_email = ?",
                (mailbox_email,),
            )
            row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.warning("Failed to read recovery email for %s: %s", mailbox_email, e)
        return None


def get_recovery_map(mailbox_emails):
    """Return {mailbox_email: recovery_email} for the given addresses."""
    emails = [e.strip().lower() for e in mailbox_emails if e]
    if not emails:
        return {}
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in emails)
            cursor.execute(
                f"SELECT mailbox_email, recovery_email FROM mailbox_recovery WHERE mailbox_email IN ({placeholders})",
                emails,
            )
            rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}
    except Exception as e:
        logger.warning("Failed to read recovery map: %s", e)
        return {}


def set_recovery_email(mailbox_email, recovery_email):
    mailbox_email = (mailbox_email or "").strip().lower()
    recovery_email = (recovery_email or "").strip().lower()
    if not mailbox_email or not recovery_email:
        return False
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO mailbox_recovery (mailbox_email, recovery_email, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(mailbox_email) DO UPDATE SET
                recovery_email = excluded.recovery_email,
                updated_at = excluded.updated_at
            """,
            (mailbox_email, recovery_email, _utc_now_iso()),
        )
        conn.commit()
    return True


def delete_recovery_email(mailbox_email):
    mailbox_email = (mailbox_email or "").strip().lower()
    if not mailbox_email:
        return
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM mailbox_recovery WHERE mailbox_email = ?", (mailbox_email,)
        )
        cursor.execute(
            "DELETE FROM password_reset_tokens WHERE mailbox_email = ?",
            (mailbox_email,),
        )
        conn.commit()


def _purge_expired_reset_tokens(cursor):
    now = _utc_now_iso()
    cursor.execute(
        "DELETE FROM password_reset_tokens WHERE expires_at < ? OR used_at IS NOT NULL",
        (now,),
    )


def create_reset_token(mailbox_email):
    mailbox_email = (mailbox_email or "").strip().lower()
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_reset_token(raw_token)
    expires_at = (
        (datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_TTL_HOURS))
        .replace(microsecond=0)
        .isoformat()
    )
    with get_conn() as conn:
        cursor = conn.cursor()
        _purge_expired_reset_tokens(cursor)
        cursor.execute(
            "DELETE FROM password_reset_tokens WHERE mailbox_email = ?",
            (mailbox_email,),
        )
        cursor.execute(
            """
            INSERT INTO password_reset_tokens (token_hash, mailbox_email, expires_at, used_at, created_at)
            VALUES (?, ?, ?, NULL, ?)
            """,
            (token_hash, mailbox_email, expires_at, _utc_now_iso()),
        )
        conn.commit()
    return raw_token


def consume_reset_token(raw_token):
    if not raw_token or not isinstance(raw_token, str):
        return None
    token_hash = _hash_reset_token(raw_token.strip())
    now = _utc_now_iso()
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, mailbox_email FROM password_reset_tokens
            WHERE token_hash = ? AND used_at IS NULL AND expires_at >= ?
            """,
            (token_hash, now),
        )
        row = cursor.fetchone()
        if not row:
            return None
        token_id, mailbox_email = row
        cursor.execute(
            "UPDATE password_reset_tokens SET used_at = ? WHERE id = ?",
            (now, token_id),
        )
        conn.commit()
    return mailbox_email


def load_domain_mapping():
    mapping = {}
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.email, u.is_admin, d.domain 
                FROM users u 
                LEFT JOIN delegations d ON u.id = d.user_id
            """)
            rows = cursor.fetchall()

        for email, is_admin, domain in rows:
            email = email.lower()
            if email not in mapping:
                mapping[email] = []
            if is_admin and "*" not in mapping[email]:
                mapping[email].append("*")
            if domain and domain.lower() not in mapping[email]:
                mapping[email].append(domain.lower())
    except Exception as e:
        logger.warning("Failed to load domain mapping: %s", e)
    return mapping


def _normalize_permissions(raw_permissions):
    if not raw_permissions:
        return list(DEFAULT_PERMISSIONS)
    if isinstance(raw_permissions, str):
        try:
            raw_permissions = json.loads(raw_permissions)
        except Exception:
            return list(DEFAULT_PERMISSIONS)
    if not isinstance(raw_permissions, list):
        return list(DEFAULT_PERMISSIONS)
    normalized = []
    for permission in raw_permissions:
        if isinstance(permission, str):
            perm = permission.strip().lower()
            if perm in ALL_PERMISSIONS and perm not in normalized:
                normalized.append(perm)
    return normalized or list(DEFAULT_PERMISSIONS)


def load_user_grants():
    """Return {email: {domain: [permissions]}} for non-admin domain grants."""
    grants = {}
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.email, u.is_admin, d.domain, d.permissions
                FROM users u
                LEFT JOIN delegations d ON u.id = d.user_id
            """)
            rows = cursor.fetchall()

        for email, is_admin, domain, permissions in rows:
            email = email.lower()
            if is_admin:
                continue
            if not domain:
                continue
            domain = domain.lower()
            if email not in grants:
                grants[email] = {}
            grants[email][domain] = _normalize_permissions(permissions)
    except Exception as e:
        logger.warning("Failed to load user grants: %s", e)
    return grants


def load_delegations_detail():
    """Return structured delegation records for admin UI/API."""
    mapping = load_domain_mapping()
    grant_map = load_user_grants()
    contact_map = get_users_contact_map()
    records = []
    for email, domains in mapping.items():
        is_admin = "*" in domains
        domain_list = [d for d in domains if d != "*"]
        grant_rows = []
        for domain in domain_list:
            grant_rows.append(
                {
                    "domain": domain,
                    "permissions": grant_map.get(email, {}).get(
                        domain, list(DEFAULT_PERMISSIONS)
                    ),
                }
            )
        contact_email = contact_map.get(email)
        records.append(
            {
                "email": email,
                "contact_email": contact_email,
                "notification_email": resolve_notification_email(email, contact_email),
                "is_admin": is_admin,
                "domains": domains,
                "grants": grant_rows,
            }
        )
    return records


def get_users_contact_map():
    """Return {login_identifier: contact_email} for all users."""
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT email, contact_email FROM users")
            rows = cursor.fetchall()
        return {
            (email or "").lower(): (contact or "").strip().lower() or None
            for email, contact in rows
            if email
        }
    except Exception as e:
        logger.warning("Failed to load user contact map: %s", e)
        return {}


def get_user_contact_email(login_identifier):
    return get_users_contact_map().get((login_identifier or "").strip().lower())


def resolve_notification_email(login_identifier, contact_email=None):
    """Return a deliverable email for notifications, or None."""
    from utils.validators import is_email_identifier

    login_identifier = (login_identifier or "").strip().lower()
    if contact_email is None:
        contact_email = get_user_contact_email(login_identifier)
    else:
        contact_email = (contact_email or "").strip().lower() or None

    if contact_email and is_email_identifier(contact_email):
        return contact_email
    if is_email_identifier(login_identifier):
        return login_identifier
    return None


def get_admin_notification_email():
    """Deliverable contact for ADMIN_USER when no logged-in user context exists."""
    return resolve_notification_email(get_admin_user())


def set_user_contact_email(login_identifier, contact_email, is_admin=None):
    login_identifier = (login_identifier or "").strip().lower()
    if not login_identifier:
        return False
    contact_email = (contact_email or "").strip().lower() or None
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (login_identifier,))
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE users SET contact_email = ? WHERE id = ?",
                (contact_email, row[0]),
            )
        else:
            admin_flag = 0
            if is_admin is not None:
                admin_flag = 1 if is_admin else 0
            elif login_identifier == get_admin_user():
                admin_flag = 1
            cursor.execute(
                "INSERT INTO users (email, contact_email, is_admin) VALUES (?, ?, ?)",
                (login_identifier, contact_email, admin_flag),
            )
        conn.commit()
    return True


def get_or_create_secret_key():
    # 1. Check environment variable first
    env_key = os.getenv("SECRET_KEY")
    if env_key:
        return env_key

    # 2. Check SQLite settings table
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            # Ensure the settings table exists before querying
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            conn.commit()

            cursor.execute("SELECT value FROM settings WHERE key = ?", ("SECRET_KEY",))
            row = cursor.fetchone()
            if row and row[0]:
                return row[0]

            # 3. Generate a persistent fallback secret key and write it to settings table
            random_key = secrets.token_hex(24)
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("SECRET_KEY", random_key),
            )
            conn.commit()
        invalidate_settings_cache()
        return random_key
    except Exception as e:
        # Emergency last-resort fallback
        logger.warning("Failed to read/persist SECRET_KEY, using ephemeral key: %s", e)
        return os.urandom(24).hex()


def build_portal_host(subdomain_prefix, domain):
    return f"{subdomain_prefix.strip().lower()}.{domain.strip().lower()}"


def get_branding_dir():
    return os.path.join(os.path.dirname(os.path.abspath(DATABASE_FILE)), "branding")


def get_reset_portal_cname_target():
    return (
        (get_env_config("RESET_PORTAL_CNAME_TARGET") or "").strip().lower().rstrip(".")
    )


def _row_to_reset_portal(row):
    if not row:
        return None
    from utils.themes import normalize_theme

    return {
        "domain": row[0],
        "enabled": bool(row[1]),
        "subdomain_prefix": row[2] or "",
        "portal_host": row[3] or "",
        "portal_title": row[4] or "",
        "logo_filename": row[5] or "",
        "portal_theme": normalize_theme(row[6] if len(row) > 6 else None),
    }


def get_reset_portal(domain):
    domain = domain.lower().strip()
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT domain, enabled, subdomain_prefix, portal_host, portal_title, logo_filename, portal_theme
            FROM domain_reset_portals WHERE domain = ?
            """,
            (domain,),
        )
        row = cursor.fetchone()
    return _row_to_reset_portal(row)


def get_reset_portal_by_host(host):
    host = host.lower().strip().rstrip(".")
    if not host:
        return None
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT domain, enabled, subdomain_prefix, portal_host, portal_title, logo_filename, portal_theme
            FROM domain_reset_portals
            WHERE portal_host = ? AND enabled = 1
            """,
            (host,),
        )
        row = cursor.fetchone()
    return _row_to_reset_portal(row)


def list_reset_portals():
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT domain, enabled, subdomain_prefix, portal_host, portal_title, logo_filename, portal_theme
            FROM domain_reset_portals ORDER BY domain
            """
        )
        rows = cursor.fetchall()
    return [_row_to_reset_portal(row) for row in rows]


def upsert_reset_portal(
    domain, enabled, subdomain_prefix, portal_title=None, portal_theme=None
):
    from utils.validators import validate_subdomain_prefix
    from utils.themes import normalize_theme

    domain = domain.lower().strip()
    enabled = bool(enabled)
    subdomain_prefix = (subdomain_prefix or "").strip().lower()
    portal_title = (portal_title or "").strip()
    theme = normalize_theme(portal_theme)

    if enabled and not subdomain_prefix:
        return False, "Subdomain prefix is required when the portal is enabled."
    if subdomain_prefix:
        ok, message = validate_subdomain_prefix(subdomain_prefix)
        if not ok:
            return False, message

    portal_host = (
        build_portal_host(subdomain_prefix, domain) if subdomain_prefix else ""
    )

    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO domain_reset_portals
                (domain, enabled, subdomain_prefix, portal_host, portal_title, logo_filename, portal_theme)
            VALUES (?, ?, ?, ?, ?, '', ?)
            ON CONFLICT(domain) DO UPDATE SET
                enabled = excluded.enabled,
                subdomain_prefix = excluded.subdomain_prefix,
                portal_host = excluded.portal_host,
                portal_title = excluded.portal_title,
                portal_theme = excluded.portal_theme
            """,
            (
                domain,
                1 if enabled else 0,
                subdomain_prefix,
                portal_host,
                portal_title,
                theme,
            ),
        )
        conn.commit()
    return True, ""


def set_reset_portal_logo(domain, logo_filename):
    domain = domain.lower().strip()
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE domain_reset_portals SET logo_filename = ? WHERE domain = ?",
            (logo_filename, domain),
        )
        updated = cursor.rowcount > 0
        conn.commit()
    return updated


def clear_reset_portal_logo(domain):
    portal = get_reset_portal(domain)
    if not portal or not portal.get("logo_filename"):
        return False
    logo_path = os.path.join(get_branding_dir(), domain, portal["logo_filename"])
    if os.path.isfile(logo_path):
        os.remove(logo_path)
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE domain_reset_portals SET logo_filename = '' WHERE domain = ?",
            (domain.lower().strip(),),
        )
        conn.commit()
    return True


def get_active_reset_portal_for_mailbox_domain(domain):
    portal = get_reset_portal(domain)
    if portal and portal.get("enabled") and portal.get("subdomain_prefix"):
        return portal
    return None


def build_reset_portal_url(domain, token):
    portal = get_active_reset_portal_for_mailbox_domain(domain)
    if not portal:
        return None
    scheme = "https" if use_secure_cookies() else "http"
    host = portal["portal_host"]
    return f"{scheme}://{host}/reset-password?token={token}"


def init_db(logger=None):
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                is_admin BOOLEAN NOT NULL DEFAULT 0
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delegations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                domain TEXT NOT NULL,
                permissions TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, domain)
            );
        """)

        cursor.execute("PRAGMA table_info(delegations)")
        delegation_columns = {row[1] for row in cursor.fetchall()}
        if "permissions" not in delegation_columns:
            cursor.execute("ALTER TABLE delegations ADD COLUMN permissions TEXT")
            default_permissions = json.dumps(DEFAULT_PERMISSIONS)
            cursor.execute(
                "UPDATE delegations SET permissions = ? WHERE permissions IS NULL OR permissions = ''",
                (default_permissions,),
            )
            conn.commit()
        cursor.execute("PRAGMA table_info(users)")
        user_columns = {row[1] for row in cursor.fetchall()}
        if "contact_email" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN contact_email TEXT")
            conn.commit()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mailbox_recovery (
                mailbox_email TEXT PRIMARY KEY,
                recovery_email TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT NOT NULL,
                mailbox_email TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                created_at TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS domain_reset_portals (
                domain TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                subdomain_prefix TEXT NOT NULL DEFAULT '',
                portal_host TEXT NOT NULL DEFAULT '',
                portal_title TEXT NOT NULL DEFAULT '',
                logo_filename TEXT NOT NULL DEFAULT '',
                portal_theme TEXT NOT NULL DEFAULT 'emerald'
            );
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_domain_reset_portals_host
            ON domain_reset_portals(portal_host)
            WHERE portal_host != '' AND enabled = 1
        """)
        cursor.execute("PRAGMA table_info(domain_reset_portals)")
        portal_columns = {row[1] for row in cursor.fetchall()}
        if "portal_theme" not in portal_columns:
            cursor.execute(
                "ALTER TABLE domain_reset_portals ADD COLUMN portal_theme TEXT NOT NULL DEFAULT 'emerald'"
            )
            conn.commit()
        conn.commit()

        # Perform migration from JSON if it exists
        if os.path.exists(MAPPING_FILE):
            try:
                with open(MAPPING_FILE, "r") as f:
                    mapping = json.load(f)

                for email, domains in mapping.items():
                    email = email.lower().strip()
                    if not email:
                        continue
                    is_admin = (
                        "*" in domains
                        or email in get_oidc_admin_users()
                        or email == get_admin_user()
                        or email == "admin@local"
                    )

                    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
                    user_row = cursor.fetchone()
                    if not user_row:
                        cursor.execute(
                            "INSERT INTO users (email, is_admin) VALUES (?, ?)",
                            (email, 1 if is_admin else 0),
                        )
                        user_id = cursor.lastrowid
                    else:
                        user_id = user_row[0]

                    for domain in domains:
                        domain = domain.lower().strip()
                        if domain == "*":
                            continue
                        cursor.execute(
                            "INSERT OR IGNORE INTO delegations (user_id, domain, permissions) VALUES (?, ?, ?)",
                            (user_id, domain, json.dumps(DEFAULT_PERMISSIONS)),
                        )
                conn.commit()

                # Rename mapping file to prevent future migrations
                bak_file = MAPPING_FILE + ".bak"
                os.rename(MAPPING_FILE, bak_file)
                if logger:
                    logger.info(
                        f"Successfully migrated {MAPPING_FILE} to SQLite and renamed to {bak_file}"
                    )
            except Exception as e:
                if logger:
                    logger.error(f"Failed to migrate legacy mapping file: {e}")

        migrate_settings_secrets(cursor)
        conn.commit()

        # Seed initial admin user if empty and an admin password hash exists
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        admin_count = cursor.fetchone()[0]
        cursor.execute(
            "SELECT value FROM settings WHERE key = ?", (ADMIN_PASSWORD_HASH_KEY,)
        )
        admin_hash_row = cursor.fetchone()
        if admin_count == 0 and admin_hash_row and admin_hash_row[0]:
            admin_email = get_admin_user().lower().strip()
            cursor.execute(
                "INSERT OR IGNORE INTO users (email, password_hash, is_admin) VALUES (?, ?, 1)",
                (admin_email, admin_hash_row[0]),
            )
            conn.commit()
            if logger:
                logger.info(
                    f"Seeded initial admin user '{admin_email}' into SQLite database."
                )
        conn.close()
    except Exception as e:
        if logger:
            logger.error(f"Failed to initialize database: {e}")
