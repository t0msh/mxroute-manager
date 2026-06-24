"""Tests for API catalog helpers and docs routes."""

import pytest

from utils.api_catalog import build_openapi_document, collect_api_routes


@pytest.fixture(autouse=True)
def clear_users(db_connection):
    db_connection.execute("DELETE FROM delegations")
    db_connection.execute("DELETE FROM users")
    db_connection.commit()


def test_collect_api_routes_includes_health(client):
    from app import app

    routes = collect_api_routes(app)
    paths = {route["path"] for route in routes}
    assert "/health" in paths
    assert "/api/cloudflare/dns/fix-bulk" in paths


def test_openapi_document_has_paths(client):
    from app import app

    doc = build_openapi_document(app, base_url="https://manager.example.com")
    assert doc["openapi"] == "3.0.3"
    assert "/health" in doc["paths"]
    assert "get" in doc["paths"]["/health"]


def test_api_docs_requires_admin(fresh_db, client, db_connection):
    from tests.helpers import insert_user_with_grants, prime_authenticated_session

    insert_user_with_grants(
        db_connection,
        "viewer@local",
        grants=[{"domain": "example.com", "permissions": ["dns"]}],
    )
    prime_authenticated_session(client, "viewer@local")
    assert client.get("/api/docs").status_code == 403


def test_api_docs_available_for_admin(fresh_db, client, db_connection):
    from tests.helpers import insert_user_with_grants, prime_authenticated_session

    insert_user_with_grants(db_connection, "admin@local", is_admin=True)
    prime_authenticated_session(client, "admin@local")
    response = client.get("/api/docs")
    assert response.status_code == 200
    assert b"API Reference" in response.data
