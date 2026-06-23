import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from models.db_conn import get_conn
from models.db_constants import RESET_TOKEN_TTL_HOURS

logger = logging.getLogger(__name__)


def _utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hash_reset_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def parse_mailbox_email(address):
    """Return (username, domain) for a full mailbox address, or (None, None)."""
    from utils.validators import validate_domain, validate_username, is_email_identifier

    if not address or not isinstance(address, str):
        return None, None
    address = address.strip().lower()
    if not is_email_identifier(address) or "@" not in address:
        return None, None
    username, domain = address.rsplit("@", 1)
    if not validate_username(username) or not validate_domain(domain):
        return None, None
    return username, domain


def get_recovery_email(mailbox_email):
    mailbox_email = (mailbox_email or "").strip().lower()
    if not mailbox_email:
        return None
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT recovery_email FROM mailbox_recovery WHERE mailbox_email = ?",
                (mailbox_email,),
            )
            row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.warning("Failed to read recovery email for %s: %s", mailbox_email, e)
        return None


def get_recovery_map(mailbox_emails):
    """Return {mailbox_email: recovery_email} for the given addresses."""
    emails = [e.strip().lower() for e in mailbox_emails if e]
    if not emails:
        return {}
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in emails)
            cursor.execute(
                f"SELECT mailbox_email, recovery_email FROM mailbox_recovery WHERE mailbox_email IN ({placeholders})",
                emails,
            )
            rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}
    except Exception as e:
        logger.warning("Failed to read recovery map: %s", e)
        return {}


def set_recovery_email(mailbox_email, recovery_email):
    mailbox_email = (mailbox_email or "").strip().lower()
    recovery_email = (recovery_email or "").strip().lower()
    if not mailbox_email or not recovery_email:
        return False
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO mailbox_recovery (mailbox_email, recovery_email, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(mailbox_email) DO UPDATE SET
                recovery_email = excluded.recovery_email,
                updated_at = excluded.updated_at
            """,
            (mailbox_email, recovery_email, _utc_now_iso()),
        )
        conn.commit()
    return True


def delete_recovery_email(mailbox_email):
    mailbox_email = (mailbox_email or "").strip().lower()
    if not mailbox_email:
        return
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM mailbox_recovery WHERE mailbox_email = ?", (mailbox_email,)
        )
        cursor.execute(
            "DELETE FROM password_reset_tokens WHERE mailbox_email = ?",
            (mailbox_email,),
        )
        conn.commit()


def _purge_expired_reset_tokens(cursor):
    now = _utc_now_iso()
    cursor.execute(
        "DELETE FROM password_reset_tokens WHERE expires_at < ? OR used_at IS NOT NULL",
        (now,),
    )


def create_reset_token(mailbox_email):
    mailbox_email = (mailbox_email or "").strip().lower()
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_reset_token(raw_token)
    expires_at = (
        (datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_TTL_HOURS))
        .replace(microsecond=0)
        .isoformat()
    )
    with get_conn() as conn:
        cursor = conn.cursor()
        _purge_expired_reset_tokens(cursor)
        cursor.execute(
            "DELETE FROM password_reset_tokens WHERE mailbox_email = ?",
            (mailbox_email,),
        )
        cursor.execute(
            """
            INSERT INTO password_reset_tokens (token_hash, mailbox_email, expires_at, used_at, created_at)
            VALUES (?, ?, ?, NULL, ?)
            """,
            (token_hash, mailbox_email, expires_at, _utc_now_iso()),
        )
        conn.commit()
    return raw_token


def consume_reset_token(raw_token):
    if not raw_token or not isinstance(raw_token, str):
        return None
    token_hash = _hash_reset_token(raw_token.strip())
    now = _utc_now_iso()
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, mailbox_email FROM password_reset_tokens
            WHERE token_hash = ? AND used_at IS NULL AND expires_at >= ?
            """,
            (token_hash, now),
        )
        row = cursor.fetchone()
        if not row:
            return None
        token_id, mailbox_email = row
        cursor.execute(
            "UPDATE password_reset_tokens SET used_at = ? WHERE id = ?",
            (now, token_id),
        )
        conn.commit()
    return mailbox_email
