# API example scripts

Small, copy-paste-friendly scripts that talk to MXroute Manager over the HTTP API. They assume you already created a Bearer token under **Access Control → API Tokens** with the right permissions.

Set these before running:

| Variable | Example |
| --- | --- |
| `MXM_URL` | `https://manager.example.com` (no trailing slash) |
| `MXM_TOKEN` | `mxm_…` secret from token creation |

## Scripts

| Script | Platform | Permission needed | What it does |
| --- | --- | --- | --- |
| [deploy-mailbox.ps1](deploy-mailbox.ps1) | PowerShell | `emails` on the domain | Creates one mailbox |
| [deploy-mailbox.sh](deploy-mailbox.sh) | Bash + curl | `emails` on the domain | Same, for Linux/macOS |
| [blacklist-sender.ps1](blacklist-sender.ps1) | PowerShell | `spam` on the domain | Adds an address to SpamAssassin blacklist |
| [blacklist-sender.sh](blacklist-sender.sh) | Bash + curl | `spam` on the domain | Same, for Linux/macOS |

## Create a token for scripts

1. Sign in as admin → **Access Control** → **API Tokens**.
2. Name it (e.g. `hr-automation`), pick scopes and domains.
3. Copy the `mxm_…` value immediately; it is shown once.

Narrow scopes beat admin tokens. A mailbox provisioning script only needs `emails` on one domain. Karen-blocking only needs `spam`.

Full API reference: [HTTP API](../api.md).
