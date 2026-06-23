import json
import logging
import os
import secrets

from models.db_conn import get_conn
from models.db_constants import ALL_PERMISSIONS, DEFAULT_PERMISSIONS
from models.db_settings import get_admin_user, invalidate_settings_cache

logger = logging.getLogger(__name__)


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


def load_delegations_detail():
    """Return structured delegation records for admin UI/API."""
    from utils.validators import nested_dict_get

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
                    "permissions": nested_dict_get(
                        grant_map, email, domain, default=list(DEFAULT_PERMISSIONS)
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
