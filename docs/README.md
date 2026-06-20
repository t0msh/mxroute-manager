# MXroute Manager documentation

## Setup

| Guide | Description |
| --- | --- |
| [Getting started](getting-started.md) | First deploy: clone, `.env`, Docker, login, production checklist |
| [Configuration](configuration.md) | All environment variables and in-app Settings |
| [Local admin password](admin-password.md) | How admin credentials are seeded and how to reset them |
| [Reverse proxy](reverse-proxy.md) | TLS, Nginx Proxy Manager, branded reset portals |

## Features

| Guide | Description |
| --- | --- |
| [Adding a domain](adding-a-domain.md) | Domain wizard: verification, MXroute registration, Cloudflare mail DNS |
| [Access control](access-control.md) | Delegated users, permissions, admin vs delegated operations |
| [Mailbox password reset](password-reset.md) | Login-page reset and branded per-domain portals |

## Development

| Guide | Description |
| --- | --- |
| [Testing](testing.md) | Test layers, fixtures, and how to add coverage |

## Typical paths

**Minimum viable install** - [Getting started](getting-started.md) steps 1-3, then manage mailboxes in the UI.

**Production** - Complete getting started through step 5, then [Reverse proxy](reverse-proxy.md).

**Delegated team access** - Production setup, then [Access control](access-control.md).

**Mailbox self-service reset** - [Password reset](password-reset.md) (login page only, or branded portals with Cloudflare + NPM).

Feature overview and roadmap: [main README](../README.md).

## Related guides

| Guide | Topic |
| --- | --- |
| [Getting started](getting-started.md) | First deploy from clone to login |
| [Configuration](configuration.md) | All environment variables |
| [Local admin password](admin-password.md) | Break-glass admin credentials |
| [Access control](access-control.md) | Delegated users and permissions |
| [Password reset](password-reset.md) | Mailbox self-service reset |
| [Reverse proxy](reverse-proxy.md) | TLS and Nginx Proxy Manager |
| [Testing](testing.md) | Test suite layout and how to run it |
| [Main README](../README.md) | Project overview, features, quickstart |
