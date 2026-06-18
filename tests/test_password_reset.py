"""Tests for mailbox recovery and password reset token helpers."""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_FILE"] = _tmp.name

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import db  # noqa: E402
from utils.validators import validate_mailbox_password, validate_recovery_email  # noqa: E402


def test_recovery_email_crud():
    db.init_db()
    mailbox = "alex@example.com"
    recovery = "personal@gmail.com"

    assert db.get_recovery_email(mailbox) is None

    ok = db.set_recovery_email(mailbox, recovery)
    assert ok is True
    assert db.get_recovery_email(mailbox) == recovery

    recovery_map = db.get_recovery_map([mailbox, "missing@example.com"])
    assert recovery_map[mailbox] == recovery
    assert "missing@example.com" not in recovery_map

    db.delete_recovery_email(mailbox)
    assert db.get_recovery_email(mailbox) is None


def test_reset_token_lifecycle():
    db.init_db()
    mailbox = "user@example.com"
    token = db.create_reset_token(mailbox)
    assert isinstance(token, str) and len(token) > 20

    consumed = db.consume_reset_token(token)
    assert consumed == mailbox

    assert db.consume_reset_token(token) is None


def test_expired_token_rejected():
    db.init_db()
    mailbox = "expired@example.com"
    token = db.create_reset_token(mailbox)
    token_hash = db._hash_reset_token(token)
    expired_at = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(microsecond=0).isoformat()

    conn = sqlite3.connect(_tmp.name)
    conn.execute(
        "UPDATE password_reset_tokens SET expires_at = ? WHERE token_hash = ?",
        (expired_at, token_hash),
    )
    conn.commit()
    conn.close()

    assert db.consume_reset_token(token) is None


def test_parse_mailbox_email():
    username, domain = db.parse_mailbox_email("Alex@Example.COM")
    assert username == "alex"
    assert domain == "example.com"
    assert db.parse_mailbox_email("not-an-email") == (None, None)


def test_validators():
    ok, _ = validate_recovery_email("user@example.com", "backup@gmail.com")
    assert ok is True

    ok, message = validate_recovery_email("user@example.com", "user@example.com")
    assert ok is False
    assert "differ" in message.lower()

    assert validate_mailbox_password("Abcd123!") is True
    assert validate_mailbox_password("weak") is False


def test_notification_email_resolution():
    db.init_db()
    db.set_user_contact_email("billy", "billy.personal@gmail.com")
    assert db.resolve_notification_email("billy") == "billy.personal@gmail.com"
    assert db.resolve_notification_email("admin@example.com") == "admin@example.com"
    assert db.resolve_notification_email("plainuser") is None
    conn = sqlite3.connect(_tmp.name)
    conn.execute("DELETE FROM users WHERE email = ?", ("billy",))
    conn.commit()
    conn.close()


def main():
    test_recovery_email_crud()
    test_reset_token_lifecycle()
    test_expired_token_rejected()
    test_parse_mailbox_email()
    test_validators()
    test_notification_email_resolution()
    os.unlink(_tmp.name)
    print("password reset self-check passed")


if __name__ == "__main__":
    main()
