"""Periodic reset for DEMO_MODE instances."""

import logging
import os
import threading
import time

from models.db import get_conn
from services.demo_backend import reset_demo_state
from services.demo_mode import is_demo_mode

logger = logging.getLogger(__name__)

# Visitor-writable demo data in SQLite; users/settings are kept.
_DEMO_RESET_TABLES = (
    "mailbox_recovery",
    "password_reset_tokens",
    "delegations",
    "domain_reset_portals",
)


def demo_reset_interval_seconds():
    raw = os.getenv("DEMO_RESET_MINUTES", "10")
    try:
        minutes = max(1, int(raw))
    except (TypeError, ValueError):
        minutes = 10
    return minutes * 60


def reset_demo_instance():
    """Restore seeded fake MXroute/CF/NPM state and clear visitor SQLite data."""
    reset_demo_state()
    try:
        with get_conn() as conn:
            for table in _DEMO_RESET_TABLES:
                conn.execute(f"DELETE FROM {table}")
            conn.commit()
    except Exception as exc:
        logger.warning("Demo reset: failed to clear SQLite tables: %s", exc)
    logger.info("Demo instance reset to seeded state")


def start_demo_reset_scheduler(app):
    if not is_demo_mode():
        return

    interval = demo_reset_interval_seconds()

    def _loop():
        while True:
            time.sleep(interval)
            try:
                with app.app_context():
                    reset_demo_instance()
            except Exception:
                logger.exception("Scheduled demo reset failed")

    threading.Thread(target=_loop, daemon=True, name="demo-reset").start()
    logger.info("Demo reset scheduler started (every %s minutes)", interval // 60)
