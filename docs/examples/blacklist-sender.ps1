<#
.SYNOPSIS
    Add a sender to the SpamAssassin blacklist for a domain.

.DESCRIPTION
    HR asked nicely. Karen did not. Block her at the mail server instead of
    replying-all for the fifth time this week.

    Example:

        .\blacklist-sender.ps1 -Domain "example.com" -Entry "karen@hr.example.com"

    Entry can be a full address or a local part (stored as entry@domain by the API).
    Requires an API token with `spam` permission on the domain.

.NOTES
    See docs/examples/README.md
#>
[CmdletBinding()]
param(
    [string] $ManagerUrl = $env:MXM_URL,
    [string] $Token = $env:MXM_TOKEN,
    [Parameter(Mandatory = $true)]
    [string] $Domain,
    [Parameter(Mandatory = $true)]
    [string] $Entry
)

$ErrorActionPreference = "Stop"

if (-not $ManagerUrl) { throw "Set MXM_URL or pass -ManagerUrl" }
if (-not $Token) { throw "Set MXM_TOKEN or pass -Token" }

$ManagerUrl = $ManagerUrl.TrimEnd("/")
$uri = "$ManagerUrl/api/domains/$Domain/spam/blacklist"

$headers = @{
    Authorization  = "Bearer $Token"
    "Content-Type" = "application/json"
}

$body = @{ entry = $Entry } | ConvertTo-Json

Write-Host "Blacklisting '$Entry' on $Domain (Karen cannot hurt you anymore) ..."

$response = Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body $body

if (-not $response.success) {
    throw "API error: $($response.error.message)"
}

Write-Host "Added to blacklist. Peace at last."
$response.data | ConvertTo-Json -Depth 5
