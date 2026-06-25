"""Tests for per-domain DMARC policy storage and API."""

import pytest

from models.db_dmarc import (
    clear_domain_dmarc_policy,
    get_dmarc_record_for_domain,
    set_domain_dmarc_policy,
)
from tests.helpers import auth_post_headers, insert_user_with_grants, prime_authenticated_session

DOMAIN = "example.com"
CUSTOM_DMARC = "v=DMARC1; p=reject; sp=reject; aspf=r;"


@pytest.fixture(autouse=True)
def clear_dmarc_table(db_connection):
    db_connection.execute("DELETE FROM domain_dmarc_policies")
    db_connection.execute("DELETE FROM delegations")
    db_connection.execute("DELETE FROM users")
    db_connection.commit()


@pytest.fixture
def dns_delegate_token(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "dns@local",
        grants=[{"domain": DOMAIN, "permissions": ["dns"]}],
    )
    return prime_authenticated_session(client, "dns@local")


def test_get_dmarc_record_for_domain_uses_custom_override(fresh_db):
    set_domain_dmarc_policy(DOMAIN, CUSTOM_DMARC)
    assert get_dmarc_record_for_domain(DOMAIN) == CUSTOM_DMARC


def test_clear_domain_dmarc_policy_reverts_to_default(fresh_db, monkeypatch):
    monkeypatch.setenv("DMARC_RECORD", "v=DMARC1; p=none; sp=none; adkim=r; aspf=r;")
    set_domain_dmarc_policy(DOMAIN, CUSTOM_DMARC)
    clear_domain_dmarc_policy(DOMAIN)
    assert get_dmarc_record_for_domain(DOMAIN) == "v=DMARC1; p=none; sp=none; adkim=r; aspf=r;"


def test_dmarc_policy_get_and_patch(fresh_db, client, dns_delegate_token):
    get_resp = client.get(f"/api/domains/{DOMAIN}/dmarc-policy")
    assert get_resp.status_code == 200
    payload = get_resp.get_json()["data"]
    assert payload["custom"] is False
    assert "default" in payload

    patch_resp = client.patch(
        f"/api/domains/{DOMAIN}/dmarc-policy",
        headers=auth_post_headers(dns_delegate_token),
        json={"dmarc_record": CUSTOM_DMARC},
    )
    assert patch_resp.status_code == 200
    saved = patch_resp.get_json()["data"]
    assert saved["custom"] is True
    assert saved["effective"] == CUSTOM_DMARC

    clear_resp = client.patch(
        f"/api/domains/{DOMAIN}/dmarc-policy",
        headers=auth_post_headers(dns_delegate_token),
        json={"dmarc_record": None},
    )
    assert clear_resp.status_code == 200
    assert clear_resp.get_json()["data"]["custom"] is False


def test_dmarc_policy_patch_rejects_invalid_record(fresh_db, client, dns_delegate_token):
    response = client.patch(
        f"/api/domains/{DOMAIN}/dmarc-policy",
        headers=auth_post_headers(dns_delegate_token),
        json={"dmarc_record": "not-a-dmarc-record"},
    )
    assert response.status_code == 400
