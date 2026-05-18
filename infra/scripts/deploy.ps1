# -- LEO AI Core - Infrastructure Deploy Script ----------------------------
# Usage:
#   .\infra\scripts\deploy.ps1 -Environment shared          # provision ACR in leo-ai RG
#   .\infra\scripts\deploy.ps1 -Environment dev             # provision dev stack in leo-ai-dev RG
#   .\infra\scripts\deploy.ps1 -Environment dev -ImageTag sha-abc123
#   .\infra\scripts\deploy.ps1 -Environment dev -SubscriptionId xxxxxxxx-...
#
# Requires: az CLI logged in with Contributor on target subscription.
# Requires: bicep CLI (bundled with az CLI >= 2.20)
param(
    [Parameter(Mandatory)]
    [ValidateSet('shared', 'dev', 'val', 'prod')]
    [string]$Environment,

    [string]$SubscriptionId,
    [string]$ImageTag = 'placeholder',
    [string]$Location = 'uksouth'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# -- Switch subscription if requested --------------------------------------
if ($SubscriptionId) {
    Write-Host "Switching to subscription $SubscriptionId"
    az account set --subscription $SubscriptionId
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# -- Determine resource group and template ---------------------------------
if ($Environment -eq 'shared') {
    $ResourceGroup = 'leo-ai'
    $TemplateFile = 'infra/bicep/modules/acr.bicep'
} else {
    $ResourceGroup = "leo-ai-$Environment"
    $TemplateFile = 'infra/bicep/main.bicep'
    $ParametersFile = "infra/bicep/parameters/$Environment.bicepparam"
}

# -- Create resource group if it does not exist ----------------------------
$rgExists = az group exists --name $ResourceGroup
if ($rgExists -eq 'false') {
    Write-Host "Creating resource group $ResourceGroup in $Location"
    az group create --name $ResourceGroup --location $Location
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# -- Deploy ----------------------------------------------------------------
Write-Host "Deploying $Environment to $ResourceGroup ..."

if ($Environment -eq 'shared') {
    az deployment group create `
        --resource-group $ResourceGroup `
        --template-file $TemplateFile `
        --name "acr-$(Get-Date -Format 'yyyyMMddHHmmss')"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    # -- Single-pass Bicep deployment -----------------------------------------
    # Note: Redis Enterprise takes 20-30 min to provision; az CLI polls until done.
    Write-Host "Starting Bicep deployment (Redis Enterprise takes 20-30 min - please wait) ..."
    $deployOutput = az deployment group create `
        --resource-group $ResourceGroup `
        --template-file $TemplateFile `
        --parameters $ParametersFile `
        --parameters imageTag=$ImageTag `
        --name "deploy-$Environment-$(Get-Date -Format 'yyyyMMddHHmmss')" `
        --output json | ConvertFrom-Json

    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    # -- Show outputs ----------------------------------------------------------
    $outputs = $deployOutput.properties.outputs
    Write-Host "Deployment complete."
    Write-Host "  core-api:  https://$($outputs.coreApiFqdn.value)"
    Write-Host "  ui:        https://$($outputs.uiFqdn.value)"
    if ($outputs.acaDefaultDomain.value) {
        Write-Host "  aca mesh:  http://<app>.$($outputs.acaDefaultDomain.value) (internal service URLs)"
    }
    Write-Host "  kv:        $($outputs.kvUri.value)"
    Write-Host "  sb:        $($outputs.sbNamespaceFqdn.value)"
    Write-Host ""
    Write-Host "Next: run migrate-secrets.ps1 -Environment $Environment to push secrets to Key Vault."
}
