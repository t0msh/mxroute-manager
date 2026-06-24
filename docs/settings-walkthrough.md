# Settings tab walkthrough

The **Settings** tab is where global knobs live. Some fields are admin-only; themes and About are visible to everyone. If you are a delegated user, you will only see **Appearance** and **About**.

Think of it as the engine room: not glamorous, but this is where you tell the app how to talk to MXroute, Cloudflare, your identity provider, and the SMTP server that sends "you forgot your password again" emails.

## API reference link

At the top of **System Configuration**, admins get a link to **API reference** (`/api/docs`). That page lists every HTTP route the app exposes, with methods and paths. Use **Download OpenAPI JSON** if you want to feed the catalog into Postman, Bruno, or your own codegen ritual.

For copy-paste automation, start with [HTTP API](api.md) and the [example scripts](examples/README.md).

## OpenID Connect (OIDC)

| Field | What it does |
| --- | --- |
| **OIDC Authentication** | When on, users with email-style logins must sign in through your IdP instead of a local password. |
| **OIDC Scopes** | Space-separated scopes sent to the provider (default includes `groups` for admin-group mapping). |
| **Discovery URL** | Your provider's `.well-known/openid-configuration` URL. |
| **Callback Redirect URI** | Must match exactly what you register at the IdP (e.g. `https://manager.example.com/oidc/callback`). |
| **Client ID** | OAuth client identifier (saved in the database). |
| **Client Secret** | Env only: set `OIDC_CLIENT_SECRET` in `.env`. The UI shows configured / not configured. |
| **Administrator Users** | Comma-separated emails that always get admin on login. |
| **Administrator Group** | If the user's `groups` claim contains this value, they become admin. |

**Typical flow:** enable OIDC, set discovery URL and redirect URI, put client secret in `.env`, list admin emails or an admin group, restart the container, test login. Keep **Local Credentials Admin** configured as break-glass access. Details: [Configuration - Authentication](configuration.md#authentication), [Access control - OIDC](access-control.md#oidc-and-local-admin-together).

## MXroute server configuration

| Field | What it does |
| --- | --- |
| **MXroute Server Hostname** | Your mail server host from the MXroute panel (e.g. `something.mxrouting.net`). |
| **MXroute Portal Username** | Your DirectAdmin / MXroute account username. |
| **MXroute API Key** | Env only: `MX_API_KEY` in `.env`. Required for every mail and domain operation. |

After changing these, click **Save System Settings**. If API calls fail, verify the key in the MXroute panel and that the server hostname matches.

## Cloudflare API settings

| Field | What it does |
| --- | --- |
| **Cloudflare API Token** | Env only: `CF_API_TOKEN`. Needs DNS edit permission on zones you manage. |
| **Cloudflare Account ID** | Account ID from the Cloudflare dashboard. |

Without Cloudflare configured, DNS wizard steps, one-click fixes, bulk unhealthy DNS repair, and branded portal CNAME deploy are unavailable. The rest of the app still works for mail management.

## Local credentials admin

| Field | What it does |
| --- | --- |
| **Local Admin Username** | Break-glass admin login (default `admin`). Not the same as OIDC email unless you make it so. |
| **Local Admin Password** | Set a new password here (stored hashed in SQLite). Leave blank to keep the current hash. |

Initial password can be seeded from `ADMIN_PASSWORD` in `.env` on first boot only. Changing `.env` later does **not** update login until you reset the hash. Read [Local admin password](admin-password.md) before you lock yourself out.

## Mailbox password reset

Controls the **Reset Mailbox Password** tab on the login page (not the branded per-domain portals; those live under **Domains**).

| Field | What it does |
| --- | --- |
| **Self-Service Reset** | Enables the public reset tab on the login screen. |
| **SMTP STARTTLS** | Use STARTTLS on the SMTP connection (typical for port 587). |
| **SMTP Hostname / Port / Username / From** | Outbound mail settings for reset emails. |
| **SMTP Password** | Env only: `RESET_SMTP_PASSWORD`. Never stored in the database. |
| **Your Contact Email** | Where **Send Test Email** delivers when your admin login is a username, not an email. |

**Send Test Email** verifies SMTP without touching a mailbox. Each mailbox still needs a **recovery email** under **Email Accounts** before self-service reset works for that user.

Full workflows: [Password reset](password-reset.md).

## Save System Settings

One **Save System Settings** button at the bottom persists all admin fields above (except env-only secrets, which you change in `.env` and restart for).

Settings are cached per worker process. After saving, behaviour updates immediately in the worker that handled the save; restart the app if you run multiple Gunicorn workers and need instant consistency everywhere.

## Appearance and colorscheme

Available to **all users**. Pick a dark or light theme; the choice is stored in your browser (`localStorage`), not on the server. Delegated users can use Unicorn Puke without inflicting it on colleagues.

Gallery of all 12 themes: [Themes](themes.md).

## About

Version label, build info (when deployed with `deploy.sh`), GitHub link, license, and third-party attributions. Useful when someone asks "which build is production running?" and you would rather click **Settings** than SSH.

## Related guides

| Guide | Topic |
| --- | --- |
| [Configuration](configuration.md) | Every `.env` variable in one table |
| [Getting started](getting-started.md) | First deploy and post-login checklist |
| [HTTP API](api.md) | Scripting with Bearer tokens |
| [Access control](access-control.md) | Who can see which tabs |
| [Password reset](password-reset.md) | SMTP and branded portals |
