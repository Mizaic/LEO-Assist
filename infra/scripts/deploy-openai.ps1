# -- LEO AI Core - Azure OpenAI Account Deploy Script -----------------------
# Usage:
#   .\infra\scripts\deploy-openai.ps1
#   .\infra\scripts\deploy-openai.ps1 -SubscriptionName 'Multi Tenanted - LEO Production'
#
# Provisions shared mizaic-cds-oai in leo-prod-rg (once per subscription). All
# environments (dev, val, prod) use this endpoint. Syncs azureOpenAiEndpoint
# into infra/bicep/parameters/{dev,val,prod}.bicepparam automatically.
# Default Subscription name is Multi Tenanted - LEO Production
#
# Requires: az CLI logged in with Contributor on target subscription.
param(
    [string]$SubscriptionName = 'Multi Tenanted - LEO Production',
    [string]$Location = 'uksouth'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($SubscriptionName) {
    Write-Host "Switching to subscription $SubscriptionName"
    az account set --subscription $SubscriptionName
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$ResourceGroup = 'leo-prod-rg'
$TemplateFile = 'infra/bicep/openai.bicep'
$ParametersFile = 'infra/bicep/parameters/openai/shared.bicepparam'

$rgExists = az group exists --name $ResourceGroup
if ($rgExists -eq 'false') {
    Write-Host "Creating resource group $ResourceGroup in $Location"
    az group create --name $ResourceGroup --location $Location
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Deploying shared Azure OpenAI account to $ResourceGroup ..."
$deployOutput = az deployment group create `
    --resource-group $ResourceGroup `
    --template-file $TemplateFile `
    --parameters $ParametersFile `
    --name "openai-shared-$(Get-Date -Format 'yyyyMMddHHmmss')" `
    --output json | ConvertFrom-Json

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$outputs = $deployOutput.properties.outputs
Write-Host "OpenAI deployment complete."
Write-Host "  endpoint: $($outputs.aoaiEndpoint.value)"
Write-Host "  account:  $($outputs.aoaiAccountName.value)"
Write-Host ""

& "$PSScriptRoot/sync-openai-endpoint.ps1" -Endpoint $outputs.aoaiEndpoint.value
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. List keys: az cognitiveservices account keys list --name $($outputs.aoaiAccountName.value) --resource-group $ResourceGroup"
Write-Host "  2. Set AZURE_OPENAI_API_KEY in secrets\.env and run migrate-secrets.ps1 for each environment"
Write-Host "  3. Model deployments gpt-5.4, gpt-5-mini, and gpt-5.4-nano are in the Bicep module."
