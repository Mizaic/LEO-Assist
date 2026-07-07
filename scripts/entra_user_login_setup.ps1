# -- LEO AI Core - User-login app registration (Track D.1) -----------------
# PowerShell wrapper; see entra_user_login_setup.sh for full documentation.
#
# Usage:
#   .\scripts\entra_user_login_setup.ps1 -Environment val
#   .\scripts\entra_user_login_setup.ps1 -Environment val -WriteKv
#   .\scripts\entra_user_login_setup.ps1 -AppId <guid> -FrontendUrl https://example.com
param(
    [ValidateSet('dev', 'val', 'prod', '')]
    [string]$Environment = '',

    [string]$FrontendUrl = '',
    [string]$DisplayName = '',
    [string]$AppId = '',
    [switch]$IncludeLocalhost,
    [string]$SecretName = '',
    [switch]$WriteKv,
    [switch]$SkipSecret
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path $PSScriptRoot -Parent

function Get-DefaultDisplayName {
    param([string]$EnvName)
    switch ($EnvName) {
        'dev'  { return 'Mizaic LEO AI Dev' }
        'val'  { return 'Mizaic LEO AI Val' }
        'prod' { return 'Mizaic LEO AI Prod' }
        default { return "Mizaic LEO AI $EnvName" }
    }
}

function Read-FrontendUrlFromBicepparam {
    param([string]$EnvName)
    $paramFile = Join-Path $RepoRoot "infra/bicep/parameters/$EnvName.bicepparam"
    if (-not (Test-Path $paramFile)) {
        throw "Bicepparam not found: $paramFile"
    }
    $content = Get-Content -Raw -Path $paramFile
    if ($content -notmatch "param frontendUrl = '([^']+)'") {
        throw "frontendUrl not found in $paramFile"
    }
    return $Matches[1].TrimEnd('/')
}

function Normalize-FrontendUrl {
    param([string]$Url)
    $normalized = $Url.TrimEnd('/')
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        throw 'frontendUrl is empty'
    }
    if ($normalized -notmatch '^https?://') {
        throw "frontendUrl must start with http:// or https:// (got: $normalized)"
    }
    return $normalized
}

function Merge-RedirectUris {
    param([string]$ExistingJson, [string[]]$Wanted)
    $existing = @()
    if ($ExistingJson -and $ExistingJson -ne 'null') {
        $parsed = $ExistingJson | ConvertFrom-Json
        if ($parsed -is [System.Array]) {
            $existing = @($parsed)
        } elseif ($parsed) {
            $existing = @([string]$parsed)
        }
    }
    $merged = [System.Collections.Generic.List[string]]::new()
    foreach ($uri in ($Wanted + $existing)) {
        if ($uri -and -not $merged.Contains($uri)) {
            $merged.Add($uri)
        }
    }
    return ,@($merged.ToArray())
}

function Wait-ForApp {
    param([string]$TargetAppId)
    foreach ($attempt in 1..5) {
        az ad app show --id $TargetAppId --query appId -o tsv 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 2
    }
    throw "App $TargetAppId is not visible yet in Entra ID."
}

function Patch-AppSettingsViaGraph {
    param(
        [string]$ObjectId,
        [string]$ClientId,
        [string[]]$UriList
    )
    if ($UriList.Count -eq 0) {
        throw 'No redirect URIs to apply.'
    }
    $body = @{
        web = @{
            redirectUris = $UriList
            implicitGrantSettings = @{
                enableAccessTokenIssuance = $false
                enableIdTokenIssuance = $false
            }
        }
        signInAudience = 'AzureADMultipleOrgs'
        groupMembershipClaims = 'SecurityGroup'
        api = @{ requestedAccessTokenVersion = 2 }
        identifierUris = @("api://$ClientId")
    } | ConvertTo-Json -Compress -Depth 6
    $tmp = [System.IO.Path]::GetTempFileName()
    [System.IO.File]::WriteAllText($tmp, $body)
    try {
        az rest --method PATCH `
            --url "https://graph.microsoft.com/v1.0/applications/$ObjectId" `
            --headers "Content-Type=application/json" `
            --body "@$tmp" `
            --output none
        if ($LASTEXITCODE -ne 0) { throw "Graph PATCH failed for application $ObjectId" }
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
}

if (-not $Environment -and -not $FrontendUrl -and -not $AppId) {
    throw 'Set -Environment or -FrontendUrl (or -AppId with -FrontendUrl).'
}

if ($IncludeLocalhost -and $Environment -and $Environment -ne 'dev') {
    throw 'Refusing -IncludeLocalhost for non-dev environment (DC-DEP-001).'
}

if (-not $FrontendUrl) {
    if (-not $Environment) {
        throw '-FrontendUrl is required when -Environment is not set.'
    }
    $FrontendUrl = Read-FrontendUrlFromBicepparam -EnvName $Environment
}
$FrontendUrl = Normalize-FrontendUrl -Url $FrontendUrl
$RedirectUri = "$FrontendUrl/auth/callback"

if (-not $DisplayName) {
    $DisplayName = if ($Environment) { Get-DefaultDisplayName -EnvName $Environment } else { 'Mizaic LEO AI' }
}

if (-not $SecretName) {
    $SecretName = if ($Environment) { "$Environment-api" } else { 'leo-api' }
}

Write-Host '=== LEO user-login app registration (Track D.1) ==='
Write-Host "  display name:  $DisplayName"
Write-Host "  redirect URI:  $RedirectUri"
if ($IncludeLocalhost) {
    Write-Host '  also adding:   http://localhost:3000/auth/callback'
}

if (-not $AppId) {
    $existing = az ad app list --display-name $DisplayName --query '[0].appId' -o tsv 2>$null
    if ($existing -and $existing -ne 'None') {
        $AppId = $existing
        Write-Host "  found existing app: $AppId"
    }
}

$redirects = @($RedirectUri)
if ($IncludeLocalhost) {
    $redirects += 'http://localhost:3000/auth/callback'
}

if (-not $AppId) {
    Write-Host ''
    Write-Host 'Creating app registration ...'
    $createArgs = @(
        'ad', 'app', 'create',
        '--display-name', $DisplayName,
        '--sign-in-audience', 'AzureADMultipleOrgs',
        '--enable-access-token-issuance', 'false',
        '--enable-id-token-issuance', 'false',
        '--web-redirect-uris', @redirects,
        '--query', 'appId',
        '-o', 'tsv'
    )
    $AppId = az @createArgs
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($AppId)) {
        throw 'Failed to create app registration'
    }
    Write-Host "  created app id: $AppId"
} else {
    Write-Host ''
    Write-Host "Updating app registration $AppId ..."
}

Wait-ForApp -TargetAppId $AppId

az ad sp create --id $AppId --output none 2>$null

$existingRedirects = az ad app show --id $AppId --query 'web.redirectUris' -o json
$uriList = Merge-RedirectUris -ExistingJson $existingRedirects -Wanted $redirects
$objectId = az ad app show --id $AppId --query id -o tsv
if ([string]::IsNullOrWhiteSpace($objectId) -or $objectId -eq 'None') {
    throw "Could not resolve Entra object id for app $AppId"
}

Write-Host ''
Write-Host 'Applying redirect URIs and manifest settings (Graph API) ...'
Patch-AppSettingsViaGraph -ObjectId $objectId -ClientId $AppId -UriList $uriList

$TenantId = az account show --query tenantId -o tsv
$ClientSecret = ''

if (-not $SkipSecret) {
    Write-Host ''
    Write-Host "Creating client secret (display name: $SecretName) ..."
    $ClientSecret = az ad app credential reset `
        --id $AppId `
        --display-name $SecretName `
        --years 1 `
        --query password -o tsv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create client secret' }
    Write-Host '  secret created (store immediately; not shown again)'
}

if ($WriteKv) {
    if (-not $Environment) {
        throw '-WriteKv requires -Environment.'
    }
    $kvName = "mizaicai-$Environment-kv"
    Write-Host ''
    Write-Host "Writing azure-ad-* secrets to Key Vault $kvName ..."
    az keyvault secret set --vault-name $kvName --name 'azure-ad-client-id' --value $AppId --output none
    az keyvault secret set --vault-name $kvName --name 'azure-ad-tenant-id' --value $TenantId --output none
    if ($ClientSecret) {
        az keyvault secret set --vault-name $kvName --name 'azure-ad-client-secret' --value $ClientSecret --output none
    } else {
        Write-Host '  skipped azure-ad-client-secret (-SkipSecret)'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Failed to write Key Vault secrets' }
}

Write-Host ''
Write-Host '=== Done ================================================================'
Write-Host "  AZURE_AD_TENANT_ID=$TenantId"
Write-Host "  AZURE_AD_CLIENT_ID=$AppId"
if ($ClientSecret) {
    Write-Host '  AZURE_AD_CLIENT_SECRET=<created>'
}
Write-Host ''
Write-Host 'Add to secrets/.env (if not using -WriteKv), then migrate-secrets.ps1:'
Write-Host "  AZURE_AD_TENANT_ID=$TenantId"
Write-Host "  AZURE_AD_CLIENT_ID=$AppId"
if ($ClientSecret) {
    Write-Host "  AZURE_AD_CLIENT_SECRET=$ClientSecret"
}
Write-Host ''
Write-Host 'Optional: admin portal Graph permissions (Track D.4):'
Write-Host "  USER_LOGIN_APP_ID=$AppId REDIRECT_URI=$RedirectUri ./scripts/entra_user_login_graph_perms.sh"
