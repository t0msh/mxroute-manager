"""Tests for the DB-backed settings cache in models.db."""

import sqlite3

import pytest

from models import db as db_module


@pytest.fixture
def isolated_settings_db(tmp_path, monkeypatch):
    """Dedicated DB so cache staleness tests do not affect other tests."""
    path = str(tmp_path / "settings.db")
    monkeypatch.setenv("DATABASE_FILE", path)
    monkeypatch.setattr(db_module, "DATABASE_FILE", path)
    db_module.invalidate_settings_cache()
    db_module.init_db()
    yield path
    db_module.invalidate_settings_cache()


def _set(path, key, value):
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()
    conn.close()


def test_settings_cache_serves_stale_until_invalidated(isolated_settings_db):
    path = isolated_settings_db

    _set(path, "MX_SERVER", "host1")
    assert db_module.get_config_value("MX_SERVER") == "host1"
    _set(path, "MX_SERVER", "host2")
    assert db_module.get_config_value("MX_SERVER") == "host1", (
        "expected stale cache hit"
    )

    db_module.invalidate_settings_cache()
    assert db_module.get_config_value("MX_SERVER") == "host2"


def test_settings_cache_falls_back_to_default(isolated_settings_db):
    assert db_module.get_config_value("DOES_NOT_EXIST", "fallback") == "fallback"


def test_env_only_secrets_bypass_db_and_cache(isolated_settings_db, monkeypatch):
    monkeypatch.setenv("MX_API_KEY", "env-secret")
    _set(isolated_settings_db, "MX_API_KEY", "db-secret")
    assert db_module.get_config_value("MX_API_KEY") == "env-secret"


def test_reset_smtp_password_reads_env_first(isolated_settings_db, monkeypatch):
    monkeypatch.setenv("RESET_SMTP_PASSWORD", "from-env")
    _set(isolated_settings_db, "RESET_SMTP_PASSWORD", "from-db")
    assert db_module.get_reset_smtp_password() == "from-env"


def test_reset_smtp_password_falls_back_to_legacy_db(isolated_settings_db, monkeypatch):
    monkeypatch.delenv("RESET_SMTP_PASSWORD", raising=False)
    _set(isolated_settings_db, "RESET_SMTP_PASSWORD", "legacy-db-password")
    assert db_module.get_reset_smtp_password() == "legacy-db-password"
    assert db_module.is_secret_configured("RESET_SMTP_PASSWORD") is True


def test_migrate_settings_secrets_keeps_legacy_smtp_password_without_env(
    isolated_settings_db, monkeypatch
):
    monkeypatch.delenv("RESET_SMTP_PASSWORD", raising=False)
    _set(isolated_settings_db, "RESET_SMTP_PASSWORD", "legacy-db-password")

    with db_module.get_conn() as conn:
        db_module.migrate_settings_secrets(conn.cursor())
        conn.commit()

    with db_module.get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", ("RESET_SMTP_PASSWORD",)
        ).fetchone()
    assert row is not None
    assert row[0] == "legacy-db-password"


def test_migrate_settings_secrets_removes_legacy_smtp_password_when_env_set(
    isolated_settings_db, monkeypatch
):
    monkeypatch.setenv("RESET_SMTP_PASSWORD", "from-env")
    _set(isolated_settings_db, "RESET_SMTP_PASSWORD", "legacy-db-password")

    with db_module.get_conn() as conn:
        db_module.migrate_settings_secrets(conn.cursor())
        conn.commit()

    with db_module.get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", ("RESET_SMTP_PASSWORD",)
        ).fetchone()
    assert row is None
    assert db_module.get_reset_smtp_password() == "from-env"


def test_migrate_settings_secrets_force_syncs_admin_password(
    isolated_settings_db, monkeypatch
):
    from werkzeug.security import check_password_hash, generate_password_hash

    old_hash = generate_password_hash("OldPass1!")
    _set(isolated_settings_db, db_module.ADMIN_PASSWORD_HASH_KEY, old_hash)

    with db_module.get_conn() as conn:
        conn.execute(
            "INSERT INTO users (email, password_hash, is_admin) VALUES (?, ?, 1)",
            ("admin", old_hash),
        )
        conn.commit()

    monkeypatch.setenv("ADMIN_PASSWORD", "NewPass2!")
    monkeypatch.setenv("ADMIN_PASSWORD_FORCE_SYNC", "true")

    with db_module.get_conn() as conn:
        db_module.migrate_settings_secrets(conn.cursor())
        conn.commit()

    new_hash = db_module.get_admin_password_hash()
    assert check_password_hash(new_hash, "NewPass2!")
    assert not check_password_hash(new_hash, "OldPass1!")

    with db_module.get_conn() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE email = ?", ("admin",)
        ).fetchone()
    assert check_password_hash(row[0], "NewPass2!")
