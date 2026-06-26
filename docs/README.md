# MXroute Manager documentation

Welcome to the manual. The [main README](https://github.com/t0msh/mxroute-manager/blob/dev/README.md) is the billboard; this folder is the tour where we explain which button does what, which env var wakes up Cloudflare, and how to blacklist Karen from HR without opening the UI.

Everything here is Markdown in the repository so docs ship in the same pull request as the code they describe.

**Browse online:** [t0msh.github.io/mxroute-manager](https://t0msh.github.io/mxroute-manager/) (published from `main` via MkDocs Material + GitHub Pages).

**Build locally:**

```bash
pip install -r requirements-dev.txt
mkdocs serve
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) for live reload while editing.

## Setup

| Guide | Description |
| --- | --- |
| [Getting started](getting-started.md) | First deploy: clone, `.env`, Docker or `deploy.sh`, login, production checklist |
| [Configuration](configuration.md) | All environment variables and how they map to the UI |
| [Settings walkthrough](settings-walkthrough.md) | Every field on the **Settings** tab, explained |
| [Local admin password](admin-password.md) | How admin credentials are seeded and how to reset them |
| [Reverse proxy](reverse-proxy.md) | TLS, reverse proxy backends, branded reset portals |

## Features

| Guide | Description |
| --- | --- |
| [Adding a domain](adding-a-domain.md) | Domain wizard: verification, MXroute registration, Cloudflare mail DNS |
| [DNS health checks](dns-health.md) | What each DNS check means, SPF/DMARC rules, per-domain DMARC |
| [Bulk mailbox CSV](bulk-mailbox-csv.md) | Import and export mailboxes in spreadsheet-friendly batches |
| [Fleet overview](fleet-overview.md) | Dashboard table of all domains, cached health and counts |
| [Access control](access-control.md) | Delegated users, API tokens, permissions, admin vs delegated operations |
| [HTTP API](api.md) | Bearer tokens, curl recipes, route overview |
| [API example scripts](examples/README.md) | PowerShell and Bash: deploy mailbox, blacklist sender |
| [Mailbox password reset](password-reset.md) | Login-page reset and branded per-domain portals |
| [Notifications](notifications.md) | Audit event alerts, DNS health monitoring, quota alerts, Apprise targets |
| [Audit logs](audit-logs.md) | Browse, filter, download CSV/JSONL |

## UI reference

| Guide | Description |
| --- | --- |
| [App tour](app-tour.md) | Screenshots of every main tab, modals, and reset portal |
| [Themes](themes.md) | All 12 workspace themes on the login screen |

## Development and meta

| Guide | Description |
| --- | --- |
| [Testing](testing.md) | Test layers, fixtures, and how to add coverage |
| [Frontend app scripts](frontend-app-scripts.md) | Split `static/js/app/` files and script load order |

## Typical paths

**Minimum viable install** - [Getting started](getting-started.md) steps 1-3, then manage mailboxes in the UI.

**Production** - Complete getting started through step 5, then [Reverse proxy](reverse-proxy.md).

**Delegated team access** - Production setup, then [Access control](access-control.md).

**Automation / scripting** - [HTTP API](api.md) and [example scripts](examples/README.md).

**Mailbox self-service reset** - [Password reset](password-reset.md) (login page only, or branded portals with Cloudflare + a reverse proxy backend).

**"What does this Settings toggle do?"** - [Settings walkthrough](settings-walkthrough.md).

Feature overview with more personality: [main README](https://github.com/t0msh/mxroute-manager/blob/dev/README.md).

## Related guides

| Guide | Topic |
| --- | --- |
| [Getting started](getting-started.md) | First deploy from clone to login |
| [Configuration](configuration.md) | All environment variables |
| [Settings walkthrough](settings-walkthrough.md) | Settings tab field by field |
| [HTTP API](api.md) | Scripting with API tokens |
| [API examples](examples/README.md) | PowerShell and Bash scripts |
| [Local admin password](admin-password.md) | Break-glass admin credentials |
| [Access control](access-control.md) | Delegated users, API tokens, permissions |
| [Audit logs](audit-logs.md) | Download and filter audit trail |
| [Fleet overview](fleet-overview.md) | Multi-domain dashboard table |
| [Password reset](password-reset.md) | Mailbox self-service reset |
| [App tour](app-tour.md) | UI screenshots and modals |
| [Themes](themes.md) | Login screen theme gallery |
| [Reverse proxy](reverse-proxy.md) | TLS and reverse proxy backends |
| [Testing](testing.md) | Test suite layout and how to run it |
| [Frontend app scripts](frontend-app-scripts.md) | Split `static/js/app/` files and script load order |
| [Main README](https://github.com/t0msh/mxroute-manager/blob/dev/README.md) | Project overview, features, quickstart |
