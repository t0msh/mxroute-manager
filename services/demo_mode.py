"""Demo instance helpers — simulated MXroute/Cloudflare/NPM with no real side effects."""

import os

DEMO_DOMAINS = frozenset({
    "example.com",
    "notarealsite.org",
    "demo.net",
})

VERIFY_RECORD = {"name": "mxverify", "value": "mxroute-verify=demo-instance"}

MX_DNS_TEMPLATE = {
    "mx_records": [{"hostname": "mail.demo.mxroute.test", "priority": 10}],
    "spf": {"value": "v=spf1 include:mxroute.com ~all"},
    "dkim": {"name": "default._domainkey", "value": "v=DKIM1; k=rsa; p=demo"},
}


def is_demo_mode():
    return (os.getenv("DEMO_MODE", "false") or "false").lower() in ("true", "1", "yes")


def is_demo_domain(domain):
    return (domain or "").lower().strip() in DEMO_DOMAINS
