"""Regression tests that admin route modules register on the blueprint."""


def test_admin_settings_routes_registered():
    from app import app

    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/quota" in rules
    assert "/api/admin/settings" in rules
    assert "/api/admin/logs" in rules
    assert "/api/admin/logs/download" in rules
    assert "/api/admin/api-tokens" in rules
