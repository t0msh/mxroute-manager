# Mailbox password reset

MXroute Manager offers two **self-service** paths for mailbox owners to reset their password without an administrator. Both use the same backend: recovery email verification, single-use hashed tokens, SMTP delivery, and MXroute API password updates.

| Path | Where users go | Best for |
| --- | --- | --- |
| **Login-page reset** | Main app URL → **Reset Mailbox Password** tab | Single manager hostname; quick setup |
| **Branded reset portal** | Per-domain subdomain (e.g. `https://reset.example.com`) | Customer-facing branding; isolates reset traffic per domain |

You can enable one or both. If a domain has an active branded portal, reset emails for mailboxes on that domain link to the portal URL instead of the main app.

## Shared requirements

Both paths need the same foundations:

### 1. SMTP

Configure outbound mail in **Settings → Mailbox Password Reset** or via environment variables (`RESET_SMTP_*`). Use **Test SMTP** in Settings to verify delivery.

See [Configuration - Mailbox password reset](configuration.md#mailbox-password-reset) for all variables. `RESET_SMTP_PASSWORD` is **environment-only** and is not stored from the Settings form.

### 2. Enable self-service reset

Turn on **Self-Service Reset** in Settings or set `MAILBOX_RESET_ENABLED=true`. The login tab and branded portals stay hidden until SMTP is configured and this flag is on.

### 3. Recovery email per mailbox

Each mailbox that should be able to reset must have a **recovery email** - a separate address where the reset link is sent.

Set it when creating a mailbox or via **Email Accounts → Actions → Recovery email**.

Rules:

- Must be a valid email address.
- Must **not** be the same as the mailbox address (prevents self-sent loops).

Without a recovery email, reset requests are accepted silently but no email is sent (see [Security](#security) below).

### 4. Password rules

New passwords must meet MXroute Manager’s validation (8+ characters, upper, lower, number, special character) before the app calls the MXroute API.

---

## Login-page reset

The main application login screen has a **Reset Mailbox Password** tab alongside normal sign-in.

### User flow

1. User opens your manager URL (e.g. `https://mxtools.example.com/login`).
2. Switches to **Reset Mailbox Password**.
3. Enters their full mailbox address (`user@domain.com`).
4. Receives a generic success message regardless of whether the mailbox exists.
5. If eligible, an email arrives at the **recovery address** with a link to `/reset-password?token=…` on the **main app host**.
6. User sets a new password on that page; the token is consumed and the mailbox password is updated via MXroute.

### Configuration summary

| Setting | Location |
| --- | --- |
| Enable feature | Settings → Self-Service Reset, or `MAILBOX_RESET_ENABLED` |
| SMTP | Settings or `RESET_SMTP_*` env vars |
| Recovery emails | **Email Accounts** per mailbox |

No Cloudflare or Nginx Proxy Manager is required for this path.

### When reset links use the main app

If **no branded portal** is enabled for the mailbox’s domain, `build_reset_portal_url` returns nothing and the email link points at the main application’s `/reset-password` endpoint.

---

## Branded reset portals

A branded portal is a **dedicated hostname** for one mail domain (e.g. `reset.customer.com` for mailboxes `@customer.com`). Visitors see your logo, title, and theme - not the full MXroute Manager UI.

### User flow

1. User visits `https://reset.customer.com` (or your chosen subdomain).
2. Enters their mailbox address (`user@customer.com`).
3. Same generic response and email flow as the login page.
4. Reset email links to `https://reset.customer.com/reset-password?token=…` when the portal is enabled for that domain.
5. Only mailboxes on the portal’s domain can complete a reset through that host (other domains receive the generic response with no email).

### Admin setup

1. Configure [SMTP and enable self-service reset](#shared-requirements). Set **your contact email** in Settings (admins) or Access Control (delegated users); portal deploy uses the logged-in user's contact email for the `reset@{domain}` forwarder.
2. Configure Cloudflare and [Nginx Proxy Manager](reverse-proxy.md) (`CF_*`, `NPM_*`, `RESET_PORTAL_CNAME_TARGET`).
3. Open **Domains**, select the domain, and expand **Password Reset Portal**.
4. Set subdomain prefix (e.g. `reset`), title, theme, and optional logo.
5. Click **Deploy Portal** to save settings, create the `reset@{domain}` forwarder on MXroute, publish the Cloudflare CNAME, and create the NPM proxy host with TLS.

**Branded From address:** When a portal is enabled for a domain, password reset emails use `reset@{domain}` as the sender (display name = portal title, or “Password Reset”). MXroute requires that address to exist locally; deploy creates `reset@{domain}` as a forwarder to **your** contact email unless the domain already has a catch-all that satisfies sender verification. The global `RESET_SMTP_*` credentials are still used for SMTP authentication.

See [MXroute sender verification](#mxroute-sender-verification-from-addresses) for why this is required and how the app handles it.

Disabling the portal or running teardown removes DNS and NPM resources when automation is configured. The `reset@{domain}` forwarder is left in place; delete it manually under **Forwarders** if you no longer need it.

Detailed deploy steps: [Reverse proxy - Branded reset portals](reverse-proxy.md#branded-reset-portals).

### Host-based routing

Requests to the portal hostname are resolved in middleware (`get_reset_portal_by_host`). Only public reset paths are allowed on that host - the main admin UI is not exposed on `reset.example.com`.

Allowed paths include `/`, `/reset-password`, password-reset APIs, and the public logo endpoint.

### MXroute sender verification (From addresses)

When you send mail through MXroute SMTP, the server checks whether the **From** address can be delivered **locally** on that MXroute account. If it cannot, SMTP returns **Sender verify failed**. MX records and external mail hosting do not matter; only mailboxes, forwarders, and catch-all routing on the MXroute server count.

See [MXroute: Fixing "Sender verify failed" errors](https://docs.mxroute.com/docs/troubleshooting/sender-verify-failed.html) for the upstream explanation.

#### What MXroute Manager sends

| Reset path | From address | SMTP authentication |
| --- | --- | --- |
| Login-page reset (no portal for that domain) | Global `RESET_SMTP_FROM` from Settings | Global `RESET_SMTP_USER` / `RESET_SMTP_PASSWORD` |
| Branded portal (portal enabled for that domain) | `reset@{domain}` (display name = portal title or “Password Reset”) | Same global `RESET_SMTP_*` credentials |

The SMTP username does not have to match the From address. Sender verification only requires that the From address exists on the domain in MXroute.

#### How we satisfy sender verify for branded portals

On **Deploy Portal**, the app idempotently ensures MXroute can deliver to `reset@{domain}`:

1. **Catch-all shortcut:** If the domain already has catch-all set to **Address** (forward to a mailbox) or **Blackhole**, any local address including `reset@{domain}` already passes sender verify. No extra forwarder is created; deploy logs that catch-all covers it.
2. **Forwarder (default):** Otherwise the app creates or updates `reset@{domain}` as a forwarder to the **contact email of the user deploying the portal** (Settings for admins, Access Control for delegated users). Bounces and mistaken replies land there.
3. **Teardown:** Disabling the portal does **not** delete the forwarder (harmless if you re-enable later). Remove it manually under **Forwarders** if you no longer need it.

You need a deliverable contact email on your account before deploy will run (same requirement as **Send Test Email** in Settings).

#### What we do not auto-provision

- A full **mailbox** for `reset@{domain}` (unnecessary quota use; a forwarder is enough).
- A new **catch-all** just for reset mail (too broad; only reuse an existing catch-all).
- Per-domain SMTP passwords (global `RESET_SMTP_*` stays the single auth path).

---

## Comparing the two paths

| | Login-page reset | Branded portal |
| --- | --- | --- |
| **URL** | Main app `/login` + `/reset-password` | `https://<prefix>.<domain>/` |
| **Branding** | Default MXroute Manager styling | Per-domain logo, title, theme |
| **Domain scope** | Any mailbox on the account (if recovery email set) | Only mailboxes on the portal’s domain |
| **Infrastructure** | SMTP only | SMTP + Cloudflare + NPM |
| **Email link target** | Main app, unless portal enabled for domain | Portal hostname when enabled |
| **Email From address** | Global `RESET_SMTP_FROM` | `reset@{domain}` when portal enabled |

A domain can use a branded portal while other domains on the same installation still use the main-app reset link.

---

## Security

Both paths share these controls:

| Control | Behaviour |
| --- | --- |
| **No enumeration** | Request endpoint always returns the same generic success message whether the mailbox exists, has no recovery email, or is rate-limited |
| **Rate limiting** | Per client IP (5/hour) and per mailbox address (3/hour); uses real client IP behind trusted proxies (`TRUSTED_PROXY_COUNT`) |
| **Tokens** | Random raw token in the email; only a SHA-256 hash is stored server-side |
| **Single use** | Token is marked used after a successful password change |
| **Expiry** | Tokens expire after one hour |
| **Audit** | `mailbox.reset_requested` and `mailbox.reset_completed` logged (actor `public`) |
| **Portal isolation** | Branded hosts reject confirm/request for mailboxes outside the portal domain |

Failed SMTP sends do not reveal errors to the end user; the request still returns the generic message.

---

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Reset tab hidden on login | `MAILBOX_RESET_ENABLED`, SMTP configured, `/api/public/password-reset/status` |
| No email received | Recovery email set, SMTP test in Settings, spam folder, audit log for `smtp.send_failed` |
| Link goes to wrong host | Branded portal enabled/disabled for that domain; `FORCE_HTTPS` and public URL |
| Portal deploy button missing | `CF_*`, `NPM_*`, `RESET_PORTAL_CNAME_TARGET` - [Configuration](configuration.md#branded-reset-portals) |
| Portal deploy fails on contact email | Add a contact email for your account in Settings or Access Control, or sign in with an email-based login |
| Reset email From rejected by MXroute | Ensure `reset@{domain}` forwarder exists (re-deploy portal) or domain has catch-all; see [MXroute sender verify](https://docs.mxroute.com/docs/troubleshooting/sender-verify-failed.html) |
| “Invalid or expired reset link” | Token older than 1 hour, already used, or wrong portal domain |

---

## Related guides

| Guide | Topic |
| --- | --- |
| [Configuration](configuration.md) | `MAILBOX_RESET_*`, `RESET_SMTP_*`, portal env vars |
| [Reverse proxy](reverse-proxy.md) | NPM TLS and Deploy Portal workflow |
| [Getting started](getting-started.md) | Optional features during first deploy |
| [Access control](access-control.md) | Who can set recovery emails in **Email Accounts** |
| [Testing](testing.md) | Password reset and portal isolation tests |
