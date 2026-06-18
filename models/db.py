import os
import json
import sqlite3
import secrets

from werkzeug.security import check_password_hash, generate_password_hash

DATABASE_FILE = os.getenv("DATABASE_FILE", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mxroute-manager.db"))
MAPPING_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "domain_mapping.json")

ALL_PERMISSIONS = ("dashboard", "emails", "forwarders", "spam", "dns")
DEFAULT_PERMISSIONS = list(ALL_PERMISSIONS)

ENV_ONLY_SECRET_KEYS = frozenset({
    "MX_API_KEY",
    "CF_API_TOKEN",
    "OIDC_CLIENT_SECRET",
})
MASKED_SECRET_KEYS = ENV_ONLY_SECRET_KEYS | frozenset({"ADMIN_PASSWORD", "SECRET_KEY"})
ADMIN_PASSWORD_HASH_KEY = "ADMIN_PASSWORD_HASH"
SETTINGS_UI_KEYS = [
    "OIDC_ENABLED", "OIDC_CLIENT_ID", "OIDC_DISCOVERY_URL",
    "OIDC_REDIRECT_URI", "OIDC_SCOPES", "OIDC_ADMIN_USERS", "OIDC_ADMIN_GROUP",
    "MX_SERVER", "MX_USER", "CF_ACCOUNT_ID",
    "ADMIN_USER",
]
SETTINGS_RESPONSE_KEYS = SETTINGS_UI_KEYS + sorted(MASKED_SECRET_KEYS)


def get_env_config(key, default=None):
    return os.getenv(key, default)


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
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        if row is not None:
            stored = row[0]
        _settings_cache[key] = stored
    except Exception:
        pass

    if stored is not None:
        return stored
    return get_env_config(key, default)


def get_admin_password_hash():
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (ADMIN_PASSWORD_HASH_KEY,))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
    except Exception:
        pass
    return None


def verify_admin_password(password):
    password_hash = get_admin_password_hash()
    if not password_hash:
        return False
    return check_password_hash(password_hash, password)


def set_admin_password_hash(password, admin_email=None):
    password_hash = generate_password_hash(password)
    admin_email = (admin_email or get_admin_user()).lower().strip()
    conn = sqlite3.connect(DATABASE_FILE)
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
    conn.close()
    invalidate_settings_cache()


def _looks_like_password_hash(value):
    return isinstance(value, str) and (
        value.startswith("pbkdf2:") or value.startswith("scrypt:")
    )


def migrate_settings_secrets(cursor):
    for key in ENV_ONLY_SECRET_KEYS:
        cursor.execute("DELETE FROM settings WHERE key = ?", (key,))

    cursor.execute("SELECT value FROM settings WHERE key = ?", ("ADMIN_PASSWORD",))
    legacy_password_row = cursor.fetchone()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (ADMIN_PASSWORD_HASH_KEY,))
    hash_row = cursor.fetchone()

    if legacy_password_row and legacy_password_row[0] and not _looks_like_password_hash(legacy_password_row[0]):
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
    invalidate_settings_cache()


def is_secret_configured(key):
    if key == "ADMIN_PASSWORD":
        return bool(get_admin_password_hash())
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
    return get_config_value("OIDC_ENABLED", "true").lower() == "true"


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
    return set(email.strip().lower() for email in admin_users_raw.split(",") if email.strip())


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


def load_domain_mapping():
    mapping = {}
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.email, u.is_admin, d.domain 
            FROM users u 
            LEFT JOIN delegations d ON u.id = d.user_id
        """)
        rows = cursor.fetchall()
        conn.close()
        
        for email, is_admin, domain in rows:
            email = email.lower()
            if email not in mapping:
                mapping[email] = []
            if is_admin and "*" not in mapping[email]:
                mapping[email].append("*")
            if domain and domain.lower() not in mapping[email]:
                mapping[email].append(domain.lower())
    except Exception:
        pass
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
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.email, u.is_admin, d.domain, d.permissions
            FROM users u
            LEFT JOIN delegations d ON u.id = d.user_id
        """)
        rows = cursor.fetchall()
        conn.close()

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
    except Exception:
        pass
    return grants


def load_delegations_detail():
    """Return structured delegation records for admin UI/API."""
    mapping = load_domain_mapping()
    grant_map = load_user_grants()
    records = []
    for email, domains in mapping.items():
        is_admin = "*" in domains
        domain_list = [d for d in domains if d != "*"]
        grant_rows = []
        for domain in domain_list:
            grant_rows.append({
                "domain": domain,
                "permissions": grant_map.get(email, {}).get(domain, list(DEFAULT_PERMISSIONS)),
            })
        records.append({
            "email": email,
            "is_admin": is_admin,
            "domains": domains,
            "grants": grant_rows,
        })
    return records


def get_or_create_secret_key():
    # 1. Check environment variable first
    env_key = os.getenv("SECRET_KEY")
    if env_key:
        return env_key

    # 2. Check SQLite settings table
    try:
        conn = sqlite3.connect(DATABASE_FILE)
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
            conn.close()
            return row[0]

        # 3. Generate a persistent fallback secret key and write it to settings table
        random_key = secrets.token_hex(24)
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("SECRET_KEY", random_key),
        )
        conn.commit()
        conn.close()
        invalidate_settings_cache()
        return random_key
    except Exception:
        # Emergency last-resort fallback
        return os.urandom(24).hex()


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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        conn.commit()

        # Perform migration from JSON if it exists
        if os.path.exists(MAPPING_FILE):
            try:
                with open(MAPPING_FILE, 'r') as f:
                    mapping = json.load(f)
                
                for email, domains in mapping.items():
                    email = email.lower().strip()
                    if not email:
                           continue
                    is_admin = "*" in domains or email in get_oidc_admin_users() or email == get_admin_user() or email == "admin@local"
                    
                    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
                    user_row = cursor.fetchone()
                    if not user_row:
                        cursor.execute(
                            "INSERT INTO users (email, is_admin) VALUES (?, ?)",
                            (email, 1 if is_admin else 0)
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
                            (user_id, domain, json.dumps(DEFAULT_PERMISSIONS))
                        )
                conn.commit()
                
                # Rename mapping file to prevent future migrations
                bak_file = MAPPING_FILE + ".bak"
                os.rename(MAPPING_FILE, bak_file)
                if logger:
                    logger.info(f"Successfully migrated {MAPPING_FILE} to SQLite and renamed to {bak_file}")
            except Exception as e:
                if logger:
                    logger.error(f"Failed to migrate legacy mapping file: {e}")
 
        migrate_settings_secrets(cursor)
        conn.commit()

        # Seed initial admin user if empty and an admin password hash exists
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        admin_count = cursor.fetchone()[0]
        cursor.execute("SELECT value FROM settings WHERE key = ?", (ADMIN_PASSWORD_HASH_KEY,))
        admin_hash_row = cursor.fetchone()
        if admin_count == 0 and admin_hash_row and admin_hash_row[0]:
            admin_email = get_admin_user().lower().strip()
            cursor.execute(
                "INSERT OR IGNORE INTO users (email, password_hash, is_admin) VALUES (?, ?, 1)",
                (admin_email, admin_hash_row[0])
            )
            conn.commit()
            if logger:
                logger.info(f"Seeded initial admin user '{admin_email}' into SQLite database.")
        conn.close()
    except Exception as e:
        if logger:
            logger.error(f"Failed to initialize database: {e}")
