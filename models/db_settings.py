import logging
import os

from werkzeug.security import check_password_hash, generate_password_hash

from models.db_conn import get_conn, get_env_config
from models.db_constants import (
    ADMIN_PASSWORD_HASH_KEY,
    ENV_ONLY_SECRET_KEYS,
    MASKED_SECRET_KEYS,
    SETTINGS_RESPONSE_KEYS,
)

logger = logging.getLogger(__name__)

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
