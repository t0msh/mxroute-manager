<#
.SYNOPSIS
    Create a mailbox on MXroute via MXroute Manager.

.DESCRIPTION
    Example automation script. Set MXM_URL and MXM_TOKEN, then run:

        .\deploy-mailbox.ps1 -Domain "example.com" -Username "alex" -Password "Abcd1234!"

    Or pass parameters explicitly. Requires an API token with `emails` on the domain.

.NOTES
    See docs/examples/README.md and docs/api.md
#>
[CmdletBinding()]
param(
    [string] $ManagerUrl = $env:MXM_URL,
    [string] $Token = $env:MXM_TOKEN,
    [Parameter(Mandatory = $true)]
    [string] $Domain,
    [Parameter(Mandatory = $true)]
    [string] $Username,
    [Parameter(Mandatory = $true)]
    [string] $Password,
    [int] $Quota = 1024,
    [int] $Limit = 9600,
    [string] $RecoveryEmail = ""
)

$ErrorActionPreference = "Stop"

if (-not $ManagerUrl) { throw "Set MXM_URL or pass -ManagerUrl" }
if (-not $Token) { throw "Set MXM_TOKEN or pass -Token" }

$ManagerUrl = $ManagerUrl.TrimEnd("/")
$uri = "$ManagerUrl/api/domains/$Domain/email-accounts"

$body = @{
    username = $Username
    password = $Password
    quota    = $Quota
    limit    = $Limit
}
if ($RecoveryEmail) {
    $body.recovery_email = $RecoveryEmail
}

$headers = @{
    Authorization  = "Bearer $Token"
    "Content-Type" = "application/json"
}

Write-Host "Creating mailbox ${Username}@${Domain} via $ManagerUrl ..."

$response = Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body ($body | ConvertTo-Json)

if (-not $response.success) {
    $msg = $response.error.message
    throw "API error: $msg"
}

Write-Host "Done. Mailbox ${Username}@${Domain} is live."
$response.data | ConvertTo-Json -Depth 5
