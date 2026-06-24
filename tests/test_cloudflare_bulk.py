"""Tests for bulk DNS repair."""

from unittest.mock import patch

from services.cloudflare_bulk import fix_dns_bulk


def test_fix_dns_bulk_only_unhealthy_filters_domains():
    with (
        patch("services.cloudflare_bulk.cf_is_configured", return_value=True),
        patch(
            "services.cloudflare_bulk._domain_needs_fix",
            side_effect=lambda domain: domain == "bad.com",
        ),
        patch("services.cloudflare_bulk.deploy_missing_dns_to_cf") as mock_fix,
    ):
        result = fix_dns_bulk(
            ["good.com", "bad.com"],
            only_unhealthy=True,
        )

    assert result["domains"] == ["bad.com"]
    mock_fix.assert_called_once_with("bad.com", None)


def test_fix_dns_bulk_records_errors_per_domain():
    with (
        patch("services.cloudflare_bulk.cf_is_configured", return_value=True),
        patch(
            "services.cloudflare_bulk.deploy_missing_dns_to_cf",
            side_effect=ValueError("boom"),
        ),
    ):
        result = fix_dns_bulk(["example.com"])

    assert result["results"]["example.com"]["success"] is False
    assert "boom" in result["results"]["example.com"]["error"]
