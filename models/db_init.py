"""Database schema initialization and legacy migrations."""

import json
import os
import sqlite3

from models import db as db_module


def _ensure_delegation_permissions_column(cursor, conn):
    cursor.execute("PRAGMA table_info(delegations)")
    delegation_columns = {row[1] for row in cursor.fetchall()}
    if "permissions" not in delegation_columns:
        cursor.execute("ALTER TABLE delegations ADD COLUMN permissions TEXT")
        default_permissions = json.dumps(db_module.DEFAULT_PERMISSIONS)
        cursor.execute(
            "UPDATE delegations SET permissions = ? WHERE permissions IS NULL OR permissions = ''",
            (default_permissions,),
        )
        conn.commit()


def _ensure_users_contact_email_column(cursor, conn):
    cursor.execute("PRAGMA table_info(users)")
    user_columns = {row[1] for row in cursor.fetchall()}
    if "contact_email" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN contact_email TEXT")
        conn.commit()


def _ensure_portal_theme_column(cursor, conn):
    cursor.execute("PRAGMA table_info(domain_reset_portals)")
    portal_columns = {row[1] for row in cursor.fetchall()}
    if "portal_theme" not in portal_columns:
        cursor.execute(
            "ALTER TABLE domain_reset_portals ADD COLUMN portal_theme TEXT NOT NULL DEFAULT 'emerald'"
        )
        conn.commit()


def _create_tables(cursor):
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            token_prefix TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            is_admin INTEGER NOT NULL DEFAULT 0,
            grants_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            revoked_at TEXT
        );
    """)


def _migrate_json_domain_mapping(cursor, conn, logger):
    mapping_file = db_module.MAPPING_FILE
    if not os.path.exists(mapping_file):
        return
    try:
        with open(mapping_file, "r") as f:
            mapping = json.load(f)

        for email, domains in mapping.items():
            email = email.lower().strip()
            if not email:
                continue
            is_admin = (
                "*" in domains
                or email in db_module.get_oidc_admin_users()
                or email == db_module.get_admin_user()
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
                    (user_id, domain, json.dumps(db_module.DEFAULT_PERMISSIONS)),
                )
        conn.commit()

        bak_file = mapping_file + ".bak"
        os.rename(mapping_file, bak_file)
        if logger:
            logger.info(
                f"Successfully migrated {mapping_file} to SQLite and renamed to {bak_file}"
            )
    except Exception as e:
        if logger:
            logger.error(f"Failed to migrate legacy mapping file: {e}")


def _seed_initial_admin(cursor, conn, logger):
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
    admin_count = cursor.fetchone()[0]
    cursor.execute(
        "SELECT value FROM settings WHERE key = ?",
        (db_module.ADMIN_PASSWORD_HASH_KEY,),
    )
    admin_hash_row = cursor.fetchone()
    if admin_count == 0 and admin_hash_row and admin_hash_row[0]:
        admin_email = db_module.get_admin_user().lower().strip()
        cursor.execute(
            "INSERT OR IGNORE INTO users (email, password_hash, is_admin) VALUES (?, ?, 1)",
            (admin_email, admin_hash_row[0]),
        )
        conn.commit()
        if logger:
            logger.info(
                f"Seeded initial admin user '{admin_email}' into SQLite database."
            )


def init_db(logger=None):
    try:
        conn = sqlite3.connect(db_module.DATABASE_FILE)
        cursor = conn.cursor()
        _create_tables(cursor)
        _ensure_delegation_permissions_column(cursor, conn)
        _ensure_users_contact_email_column(cursor, conn)
        _ensure_portal_theme_column(cursor, conn)
        conn.commit()

        _migrate_json_domain_mapping(cursor, conn, logger)

        db_module.migrate_settings_secrets(cursor)
        conn.commit()

        _seed_initial_admin(cursor, conn, logger)
        conn.close()
    except Exception as e:
        if logger:
            logger.error(f"Failed to initialize database: {e}")
