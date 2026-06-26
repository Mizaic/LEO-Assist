# -- LEO widget CDN - Azure Storage Static Website deploy script ------------
# Usage:
#   .\infra\scripts\deploy-widget-cdn.ps1 -Environment dev
#   .\infra\scripts\deploy-widget-cdn.ps1 -Environment val -SubscriptionId xxxxxxxx-...
#
# Provisions leoaiwidgetcdn{env} in leo-widget-cdn-{env}, enables static website
# hosting, then runs sync-widget-cdn-params.ps1 to write widgetPublicHost and
# allowedOrigins into infra/bicep/parameters/{env}.bicepparam.
#
# Run this BEFORE deploy.ps1 on greenfield environments.
#
# Before first deploy, set githubActionsPrincipalId in
# infra/widget-cdn/parameters/{env}.bicepparam to your GitHub OIDC SP object ID.
#
# Requires: az CLI logged in with Contributor on target subscription.
param(
    [Parameter(Mandatory)]
    [ValidateSet('dev', 'val', 'prod')]
    [string]$Environment,

    [string]$SubscriptionId,
    [string]$Location = 'uksouth',
    [switch]$SkipParamSync
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($SubscriptionId) {
    Write-Host "Switching to subscription $SubscriptionId"
    az account set --subscription $SubscriptionId
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$ResourceGroup = "leo-widget-cdn-$Environment"
$TemplateFile = 'infra/widget-cdn/widget-cdn.bicep'
$ParametersFile = "infra/widget-cdn/parameters/$Environment.bicepparam"

$rgExists = az group exists --name $ResourceGroup
if ($rgExists -eq 'false') {
    Write-Host "Creating resource group $ResourceGroup in $Location"
    az group create --name $ResourceGroup --location $Location
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$paramText = Get-Content -Raw -Path $ParametersFile
if ($paramText -match 'REPLACE-WITH-YOUR-SP-OBJECT-ID') {
    Write-Warning @"
githubActionsPrincipalId is still a placeholder in $ParametersFile.
Set it to your GitHub Actions OIDC service principal object ID before widget-release.yml can upload blobs.
  az ad sp show --id <AZURE_CLIENT_ID from GitHub secrets> --query id -o tsv
"@
}

Write-Host "Deploying widget CDN to $ResourceGroup ..."
$deployOutput = az deployment group create `
    --resource-group $ResourceGroup `
    --template-file $TemplateFile `
    --parameters $ParametersFile `
    --name "widget-cdn-$Environment-$(Get-Date -Format 'yyyyMMddHHmmss')" `
    --output json | ConvertFrom-Json

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$outputs = $deployOutput.properties.outputs
$accountName = $outputs.originAccountName.value

Write-Host "Enabling static website on $accountName ..."
az storage blob service-properties update `
    --account-name $accountName `
    --auth-mode login `
    --static-website `
    --index-document index.html `
    --404-document 404.html
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Static website enabled (index: index.html, 404: 404.html)."

if (-not $SkipParamSync) {
    Write-Host ""
    & "$PSScriptRoot/sync-widget-cdn-params.ps1" -Environment $Environment
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$webUrl = az storage account show `
    --name $accountName `
    --resource-group $ResourceGroup `
    --query primaryEndpoints.web `
    -o tsv
$webHost = ($webUrl -replace '^https?://', '').TrimEnd('/')

Write-Host ""
Write-Host "Widget CDN deployment complete."
Write-Host "  account:   $accountName"
Write-Host "  web host:  $webHost"
Write-Host "  bundle:    https://$webHost/v1/leo-widget.js"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Customise remaining fields in infra/bicep/parameters/$Environment.bicepparam (frontendUrl, mailFromAddress, ...)"
Write-Host "  2. Run deploy.ps1 -Environment $Environment"
Write-Host "  3. Set GitHub secrets AZURE_WIDGET_STORAGE_ACCOUNT=$accountName and WIDGET_PUBLIC_HOST=$webHost"
Write-Host "  4. Run widget-release.yml to upload bundle assets to the `$web container"
