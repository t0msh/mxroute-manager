"""Tests for mailbox recovery and password reset token helpers."""

from datetime import datetime, timedelta, timezone

from utils.validators import validate_mailbox_password, validate_recovery_email


def test_recovery_email_crud(fresh_db):
    mailbox = "alex@example.com"
    recovery = "personal@gmail.com"

    assert fresh_db.get_recovery_email(mailbox) is None

    ok = fresh_db.set_recovery_email(mailbox, recovery)
    assert ok is True
    assert fresh_db.get_recovery_email(mailbox) == recovery

    recovery_map = fresh_db.get_recovery_map([mailbox, "missing@example.com"])
    assert recovery_map[mailbox] == recovery
    assert "missing@example.com" not in recovery_map

    fresh_db.delete_recovery_email(mailbox)
    assert fresh_db.get_recovery_email(mailbox) is None


def test_reset_token_lifecycle(fresh_db):
    mailbox = "user@example.com"
    token = fresh_db.create_reset_token(mailbox)
    assert isinstance(token, str) and len(token) > 20

    consumed = fresh_db.consume_reset_token(token)
    assert consumed == mailbox

    assert fresh_db.consume_reset_token(token) is None


def test_expired_token_rejected(fresh_db, db_connection):
    mailbox = "expired@example.com"
    token = fresh_db.create_reset_token(mailbox)
    token_hash = fresh_db._hash_reset_token(token)
    expired_at = (
        (datetime.now(timezone.utc) - timedelta(hours=2))
        .replace(microsecond=0)
        .isoformat()
    )

    db_connection.execute(
        "UPDATE password_reset_tokens SET expires_at = ? WHERE token_hash = ?",
        (expired_at, token_hash),
    )
    db_connection.commit()

    assert fresh_db.consume_reset_token(token) is None


def test_parse_mailbox_email(fresh_db):
    username, domain = fresh_db.parse_mailbox_email("Alex@Example.COM")
    assert username == "alex"
    assert domain == "example.com"
    assert fresh_db.parse_mailbox_email("not-an-email") == (None, None)


def test_recovery_and_password_validators():
    ok, _ = validate_recovery_email("user@example.com", "backup@gmail.com")
    assert ok is True

    ok, message = validate_recovery_email("user@example.com", "user@example.com")
    assert ok is False
    assert "differ" in message.lower()

    assert validate_mailbox_password("Abcd123!") is True
    assert validate_mailbox_password("weak") is False


def test_notification_email_resolution(fresh_db, db_connection):
    fresh_db.set_user_contact_email("billy", "billy.personal@gmail.com")
    assert fresh_db.resolve_notification_email("billy") == "billy.personal@gmail.com"
    assert (
        fresh_db.resolve_notification_email("admin@example.com") == "admin@example.com"
    )
    assert fresh_db.resolve_notification_email("plainuser") is None
    db_connection.execute("DELETE FROM users WHERE email = ?", ("billy",))
    db_connection.commit()
