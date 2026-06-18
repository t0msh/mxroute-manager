"""Self-check for the DB-backed settings cache in models.db.

Run directly: `python tests/test_settings_cache.py`. No framework required.
Verifies: values are cached, writes are not seen until the cache is invalidated,
env fallback for missing keys, and that ENV_ONLY secrets bypass the cache/DB.
"""
import os
import sqlite3
import sys
import tempfile

# Point the module at a throwaway DB before importing it.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_FILE"] = _tmp.name

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import db  # noqa: E402


def _set(key, value):
    conn = sqlite3.connect(_tmp.name)
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def main():
    db.init_db()

    # Cached read returns the stored value, then keeps returning it after a
    # direct DB write (proving the value is served from cache).
    _set("MX_SERVER", "host1")
    assert db.get_config_value("MX_SERVER") == "host1"
    _set("MX_SERVER", "host2")
    assert db.get_config_value("MX_SERVER") == "host1", "expected stale cache hit"

    # After invalidation the new value is observed.
    db.invalidate_settings_cache()
    assert db.get_config_value("MX_SERVER") == "host2", "cache not refreshed after invalidate"

    # Missing keys fall back to the provided default (and to env when set).
    assert db.get_config_value("DOES_NOT_EXIST", "fallback") == "fallback"

    # ENV_ONLY secrets never touch the settings table/cache.
    os.environ["MX_API_KEY"] = "env-secret"
    _set("MX_API_KEY", "db-secret")
    assert db.get_config_value("MX_API_KEY") == "env-secret", "ENV_ONLY key must come from env"

    os.unlink(_tmp.name)
    print("settings cache self-check passed")


if __name__ == "__main__":
    main()
