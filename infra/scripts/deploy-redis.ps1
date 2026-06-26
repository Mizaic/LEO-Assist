# -- LEO AI Core - Azure Managed Redis Deploy Script -----------------------
# Usage:
#   .\infra\scripts\deploy-redis.ps1 -Environment dev
#   .\infra\scripts\deploy-redis.ps1 -Environment val -SubscriptionId xxxxxxxx-...
#
# Provisions mizaicai-{env}-redis in leo-ai-{env}. Run before deploy.ps1 on
# greenfield environments. First create takes 20-30 min.
#
# Requires: az CLI logged in with Contributor on target subscription.
param(
    [Parameter(Mandatory)]
    [ValidateSet('dev', 'val', 'prod')]
    [string]$Environment,

    [string]$SubscriptionId,
    [string]$Location = 'uksouth'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($SubscriptionId) {
    Write-Host "Switching to subscription $SubscriptionId"
    az account set --subscription $SubscriptionId
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$ResourceGroup = "leo-ai-$Environment"
$TemplateFile = 'infra/bicep/redis.bicep'
$ParametersFile = "infra/bicep/parameters/redis/$Environment.bicepparam"

$rgExists = az group exists --name $ResourceGroup
if ($rgExists -eq 'false') {
    Write-Host "Creating resource group $ResourceGroup in $Location"
    az group create --name $ResourceGroup --location $Location
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Deploying Redis to $ResourceGroup (20-30 min on first create) ..."
$deployOutput = az deployment group create `
    --resource-group $ResourceGroup `
    --template-file $TemplateFile `
    --parameters $ParametersFile `
    --name "redis-$Environment-$(Get-Date -Format 'yyyyMMddHHmmss')" `
    --output json | ConvertFrom-Json

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$outputs = $deployOutput.properties.outputs
Write-Host "Redis deployment complete."
Write-Host "  hostname: $($outputs.redisHostname.value):$($outputs.redisPort.value)"
Write-Host "  name:     $($outputs.redisName.value)"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. List keys: az redisenterprise database list-keys --cluster-name $($outputs.redisName.value) --resource-group $ResourceGroup"
Write-Host "  2. Set REDIS_URL=rediss://:<primaryKey>@$($outputs.redisHostname.value):$($outputs.redisPort.value) in secrets\.env"
Write-Host "  3. Run migrate-secrets.ps1 -Environment $Environment to push redis-url to Key Vault."
