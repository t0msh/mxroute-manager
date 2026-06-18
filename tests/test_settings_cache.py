"""Tests for the DB-backed settings cache in models.db."""
import os
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
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def test_settings_cache_serves_stale_until_invalidated(isolated_settings_db):
    path = isolated_settings_db

    _set(path, "MX_SERVER", "host1")
    assert db_module.get_config_value("MX_SERVER") == "host1"
    _set(path, "MX_SERVER", "host2")
    assert db_module.get_config_value("MX_SERVER") == "host1", "expected stale cache hit"

    db_module.invalidate_settings_cache()
    assert db_module.get_config_value("MX_SERVER") == "host2"


def test_settings_cache_falls_back_to_default(isolated_settings_db):
    assert db_module.get_config_value("DOES_NOT_EXIST", "fallback") == "fallback"


def test_env_only_secrets_bypass_db_and_cache(isolated_settings_db, monkeypatch):
    monkeypatch.setenv("MX_API_KEY", "env-secret")
    _set(isolated_settings_db, "MX_API_KEY", "db-secret")
    assert db_module.get_config_value("MX_API_KEY") == "env-secret"
