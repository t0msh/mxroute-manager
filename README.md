# MXroute Manager

<p align="center">
  <a href="https://github.com/t0msh/mxroute-manager/actions/workflows/test.yml"><img src="https://github.com/t0msh/mxroute-manager/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://scanaislop.com/t0msh/mxroute-manager"><img src="https://badges.scanaislop.com/score/t0msh/mxroute-manager.svg" alt="aislop score"></a>
</p>

<p align="center">
  <img src="static/logo-emerald.svg" alt="MXroute Manager logo" width="220" />
</p>

> [!NOTE]
>
> This is a control panel for MXroute. It solves personal annoyances I had with managing many domains and mailboxes, and users that forget their passwords. Full disclosure, a lot of it was written with AI help (Cursor) and then beaten into shape with tests, security review, and real-world DNS pain.
>
> It's meant to run on **your** server. Back up the SQLite database, put it behind TLS, and read [Getting started](docs/getting-started.md) before you expose it to the internet. The test suite runs in CI without live MXroute or Cloudflare keys. Sensitive paths use CSRF, rate limits, hashed credentials, and audit logging.

A self-hosted Flask app for managing MXroute domains, mailboxes, forwarders, Cloudflare DNS, delegated access, API tokens, and branded password-reset portals. One UI instead of juggling panels and API docs, and yes, it does more than you'd reasonably expect from a side project.

## Quickstart

**Requirements:** Docker and Docker Compose, plus MXroute API credentials.
> [!IMPORTANT]
> Don't forget to edit `.env`

```bash
git clone https://github.com/t0msh/mxroute-manager.git
cd mxroute-manager
cp .env.example .env
# Edit .env - see docs/getting-started.md
docker compose up --build -d
```

Or use `./deploy.sh` to sync the app to a local directory or a remote host over SSH (interactive menu; save settings in `deploy.conf` for `./deploy.sh -y` later). Details: [Getting started](docs/getting-started.md#or-use-deploysh).

Open [http://localhost:5000](http://localhost:5000) (or your server's IP) and sign in with `admin` (or `ADMIN_USER`) and your `ADMIN_PASSWORD`. The `deploy.sh` script spits out where the app is running once it's built and deployed.

Production TLS, Cloudflare, SMTP, portals: [Getting started](docs/getting-started.md)

## What you get

**Tired of five tabs, three panels, and a prayer to the DNS gods?** MXroute Manager is the absurdly over-engineered answer to a simple question: *why can't one app do all of this?*

Spoiler: it can. _And it brought friends._

### Mail, but make it civilised

Provision mailboxes like you're running a boutique ESP. Forwarders, catch-alls, domain pointers, SpamAssassin knobs (whitelist, blacklist, threshold): the whole routing circus. **Bulk CSV import and export** when you have dozens of accounts to onboard and zero patience for one-by-one forms. Per-mailbox **client setup cards** so you never dig through MXroute docs again. Recovery emails, quotas, send limits, and typed-delete confirmations, because mistakes should require commitment.

### DNS that mostly behaves

Cloudflare-aware **setup wizard**, live **health checks**, and a **bulk fix** button for when propagation lied to you. Scheduled **DNS monitoring** watches your public records and screams through Apprise when something drifts, then politely celebrates when it recovers. *(Results may vary. The internet is still the internet.)*

### Command your fleet

Dashboard **fleet overview**: every domain at a glance (mail routing, DNS status, mailbox counts). Click a row, switch context. No more spreadsheet cosplay.

### Access control for grown-ups

**Delegated users** with per-domain permissions (dashboard, mail, forwarders, spam, DNS; mix and match). **API tokens** for the automation gremlins. **OIDC** for the SSO crowd. Your intern gets emails-only on `client-a.com`; your DNS contractor gets DNS-only. Revolutionary concept: *least privilege*.

### Branded password-reset portals

Users forgot their password again? Deploy a **branded reset portal** on your own subdomain: logo, colours, the whole tradeshow booth. Self-service on the login page, or full Cloudflare + reverse-proxy glamour when you want the premium experience.

### Ops that actually notify you

**Apprise** hooks for audit events (domain deleted, mailbox nuked, admin password rotated; pick your nightmares). **Quota and send-limit alerts** before mailboxes hit the wall. Filterable **audit logs** with CSV/JSONL download for the compliance cosplay. Something happened? You'll hear about it on ntfy, Discord, Slack, email, or one of 140+ other services Apprise supports.

### Look good while you suffer

**12 themes**: dark, light, and animated rainbow options for when you're having *that* kind of Tuesday. Because deleting a mailbox at 2am shouldn't look like 2009 cPanel.

---

*Still want the sober walkthrough? The docs table below has you covered.*

## Documentation

**Online:** [t0msh.github.io/mxroute-manager](https://t0msh.github.io/mxroute-manager/) (MkDocs, published from `main`)

Index: [docs/README.md](docs/README.md)

| Area | Start here |
| --- | --- |
| First deploy | [Getting started](docs/getting-started.md) |
| Settings tab | [Settings walkthrough](docs/settings-walkthrough.md) |
| Domains and DNS | [Adding a domain](docs/adding-a-domain.md) |
| Bulk mailboxes | [Bulk CSV import/export](docs/bulk-mailbox-csv.md) |
| Team access | [Access control](docs/access-control.md) |
| Scripting | [HTTP API](docs/api.md) · [Example scripts](docs/examples/README.md) |
| Alerts and logs | [Notifications](docs/notifications.md) · [Audit logs](docs/audit-logs.md) |
| UI tour | [App tour](docs/app-tour.md) |

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

Details: [Testing](docs/testing.md) · [Frontend scripts](docs/frontend-app-scripts.md) · `mkdocs serve` for docs preview

## License

MIT. See [LICENSE](LICENSE).

## A note on MXroute

[MXroute](https://mxroute.com) is a genuinely good service. Reliable mail hosting, sensible pricing, and an API that does what it says on the tin. This project exists because *my users* forget passwords, break DNS, and occasionally need forty mailboxes provisioned before the weekend. That is not MXroute's problem. Credit where it's due.
