"""Tests for audit log download."""

import json
import uuid

import pytest

from tests.helpers import insert_user_with_grants, prime_authenticated_session
from utils import audit_log as audit_log_module


@pytest.fixture
def admin_client(client, fresh_db, db_connection):
    email = f"audit-download-{uuid.uuid4().hex[:8]}@example.com"
    insert_user_with_grants(db_connection, email, is_admin=True)
    prime_authenticated_session(client, email)
    return client


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_log_module, "LOG_DIR", str(tmp_path))
    day = "2026-06-24"
    path = tmp_path / f"{day}.log"
    entries = [
        {
            "timestamp": "2026-06-24T12:00:00+00:00",
            "user": "admin@local",
            "action": "domain.create",
            "target": "example.com",
            "details": {"outcome": "created"},
        },
        {
            "timestamp": "2026-06-24T12:01:00+00:00",
            "user": "admin@local",
            "action": "mailbox.delete",
            "target": "user@example.com",
            "details": {},
        },
    ]
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")
    return day


def test_stream_audit_csv_includes_header_and_rows(log_dir):
    chunks = list(
        audit_log_module.stream_audit_csv(audit_log_module.resolve_log_file(log_dir)[0])
    )
    body = "".join(chunks)
    lines = [line for line in body.strip().splitlines() if line]
    assert lines[0] == "timestamp,user,action,target,details"
    assert "domain.create" in body
    assert "mailbox.delete" in body


def test_download_logs_csv(admin_client, log_dir):
    response = admin_client.get(f"/api/admin/logs/download?date={log_dir}&format=csv")
    assert response.status_code == 200
    assert response.mimetype.startswith("text/csv")
    assert f"audit-{log_dir}.csv" in (response.headers.get("Content-Disposition") or "")
    body = response.get_data(as_text=True)
    assert "domain.create" in body
    assert "mailbox.delete" in body


def test_download_logs_jsonl(admin_client, log_dir):
    response = admin_client.get(f"/api/admin/logs/download?date={log_dir}&format=jsonl")
    assert response.status_code == 200
    assert response.mimetype == "application/x-ndjson"
    lines = response.get_data(as_text=True).strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["action"] == "domain.create"


def test_download_logs_requires_admin(client, fresh_db, db_connection, log_dir):
    email = f"viewer-{uuid.uuid4().hex[:8]}@example.com"
    insert_user_with_grants(
        db_connection,
        email,
        is_admin=False,
        grants=[{"domain": "example.com", "permissions": ["dns"]}],
    )
    prime_authenticated_session(client, email)
    response = client.get(f"/api/admin/logs/download?date={log_dir}&format=csv")
    assert response.status_code == 403


def test_download_logs_unknown_date(admin_client, log_dir):
    response = admin_client.get("/api/admin/logs/download?date=1999-01-01&format=csv")
    assert response.status_code == 404
