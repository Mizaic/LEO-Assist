# -- LEO AI Core - Infrastructure Deploy Script ----------------------------
# Usage:
#   .\infra\scripts\deploy.ps1 -Environment shared          # provision ACR in leo-ai RG
#   .\infra\scripts\deploy.ps1 -Environment dev             # provision dev stack in leo-ai-dev RG
#   .\infra\scripts\deploy.ps1 -Environment dev -ImageTag sha-abc123
#   .\infra\scripts\deploy.ps1 -Environment val -SubscriptionId <val-sub-id> `
#       -AcrSubscriptionId <platform-sub-id> -StorageAccountSubscriptionId <platform-sub-id>
#
# First-time greenfield (Key Vault + secrets + Entra service apps before Container Apps):
#   .\infra\scripts\deploy.ps1 -Environment val -Bootstrap -SourceFile secrets\.env
#
# Manual equivalent:
#   .\infra\scripts\deploy.ps1 -Environment val -InfrastructureOnly
#   .\scripts\entra_setup.ps1 -Environment val
#   .\infra\scripts\migrate-secrets.ps1 -Environment val -SourceFile secrets\.env
#   .\infra\scripts\deploy.ps1 -Environment val
#
# Prerequisites (per environment, before first deploy):
#   .\infra\scripts\deploy-redis.ps1 -Environment dev
#   .\infra\scripts\deploy-widget-cdn.ps1 -Environment dev
#
# Shared prerequisites (once per subscription, before any env deploy):
#   .\infra\scripts\deploy-openai.ps1
#
# Requires: az CLI logged in with Contributor on target subscription.
# migrate-secrets.ps1 also requires Key Vault Secrets Officer on the env vault.
# Bootstrap entra_setup.ps1 requires Entra admin (Application.ReadWrite.All).
# Requires: bicep CLI (bundled with az CLI >= 2.20)
param(
    [Parameter(Mandatory)]
    [ValidateSet('shared', 'dev', 'val', 'prod')]
    [string]$Environment,

    [string]$SubscriptionId,
    [string]$AcrSubscriptionId,
    [string]$StorageAccountSubscriptionId,
    [string]$ImageTag = 'placeholder',
    [string]$Location = 'uksouth',
  # Phase 1 only: Key Vault, Service Bus, managed identity (no Container Apps).
    [switch]$InfrastructureOnly,
  # Greenfield: infra -> entra_setup -> migrate-secrets -> Container Apps.
    [switch]$Bootstrap,
    [switch]$SkipEntraSetup,
    [string]$SourceFile = 'secrets\.env'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-EnvDeployment {
    param(
        [string]$EnvName,
        [string]$ResourceGroupName,
        [string]$ParametersFilePath,
        [string]$Tag,
        [bool]$IncludeContainerApps
    )

    $phaseLabel = if ($IncludeContainerApps) { 'full stack' } else { 'infrastructure only (no Container Apps)' }
    Write-Host "Deploying $EnvName ($phaseLabel) to $ResourceGroupName ..."

    $deployArgs = @(
        'deployment', 'group', 'create',
        '--resource-group', $ResourceGroupName,
        '--template-file', 'infra/bicep/main.bicep',
        '--parameters', $ParametersFilePath,
        '--parameters', "imageTag=$Tag",
        '--parameters', "deployContainerApps=$IncludeContainerApps",
        '--name', "deploy-$EnvName-$(Get-Date -Format 'yyyyMMddHHmmss')",
        '--output', 'json'
    )
    if ($AcrSubscriptionId) {
        Write-Host "ACR subscription override: $AcrSubscriptionId"
        $deployArgs += '--parameters'
        $deployArgs += "acrSubscriptionId=$AcrSubscriptionId"
    }
    if ($StorageAccountSubscriptionId) {
        Write-Host "Storage subscription override: $StorageAccountSubscriptionId"
        $deployArgs += '--parameters'
        $deployArgs += "storageAccountSubscriptionId=$StorageAccountSubscriptionId"
    }
    return az @deployArgs | ConvertFrom-Json
}

function Show-EnvDeploymentOutputs {
    param(
        [object]$DeployOutput,
        [string]$EnvName
    )

    $outputs = $DeployOutput.properties.outputs
    Write-Host "Deployment complete."
    if ($outputs.deployContainerApps.value) {
        Write-Host "  core-api:  https://$($outputs.coreApiFqdn.value)"
        Write-Host "  ui:        https://$($outputs.uiFqdn.value)"
        if ($outputs.acaDefaultDomain.value) {
            Write-Host "  aca mesh:  http://<app>.$($outputs.acaDefaultDomain.value) (internal service URLs)"
        }
    } else {
        Write-Host "  Container Apps: skipped (Key Vault + Service Bus + identity only)"
    }
    Write-Host "  kv:        $($outputs.kvUri.value)"
    Write-Host "  sb:        $($outputs.sbNamespaceFqdn.value)"
    if ($outputs.aoaiEndpoint.value) {
        Write-Host "  aoai:      $($outputs.aoaiEndpoint.value)"
    }
    if ($outputs.storageAccountUrl.value) {
        Write-Host "  storage:   $($outputs.storageAccountUrl.value) (managed identity)"
    }
    Write-Host ""
    if (-not $outputs.deployContainerApps.value) {
        Write-Host "Next:"
        Write-Host "  1. scripts/entra_setup.ps1 -Environment $EnvName"
        Write-Host "  2. migrate-secrets.ps1 -Environment $EnvName"
        Write-Host "  3. deploy.ps1 -Environment $EnvName"
        return
    }
    Write-Host "Next steps:"
    Write-Host "  1. Ensure Redis is deployed (deploy-redis.ps1) and widget CDN is deployed (deploy-widget-cdn.ps1)."
    Write-Host "  2. Ensure shared OpenAI is deployed (deploy-openai.ps1)."
    Write-Host "  3. Re-run migrate-secrets.ps1 after secret rotation (infra/scripts/migrate-secrets.ps1)."
}

# -- Switch subscription if requested --------------------------------------
if ($SubscriptionId) {
    Write-Host "Switching to subscription $SubscriptionId"
    az account set --subscription $SubscriptionId
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# -- Determine resource group and template ---------------------------------
if ($Environment -eq 'shared') {
    if ($InfrastructureOnly -or $Bootstrap) {
        Write-Error '-InfrastructureOnly and -Bootstrap apply to dev, val, and prod only.'
        exit 1
    }
    $ResourceGroup = 'leo-ai'
    $TemplateFile = 'infra/bicep/modules/acr.bicep'
} else {
    $ResourceGroup = "leo-ai-$Environment"
    $ParametersFile = "infra/bicep/parameters/$Environment.bicepparam"

    $paramText = Get-Content -Raw -Path $ParametersFile
    if ($paramText -notmatch "param widgetPublicHost = '(leoaiwidgetcdn$Environment\.[^']+)'") {
        Write-Error @"
widgetPublicHost is not set for $Environment in $ParametersFile.
Run deploy-widget-cdn.ps1 first (it syncs widgetPublicHost and allowedOrigins).
"@
        exit 1
    }
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
    exit 0
}

if ($Bootstrap) {
    $RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $entraSetupScript = Join-Path $RepoRoot 'scripts/entra_setup.ps1'

    Write-Host ""
    Write-Host "=== Bootstrap phase 1/4: infrastructure (Key Vault, no Container Apps) ==="
    $null = Invoke-EnvDeployment `
        -EnvName $Environment `
        -ResourceGroupName $ResourceGroup `
        -ParametersFilePath $ParametersFile `
        -Tag $ImageTag `
        -IncludeContainerApps $false
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    if ($SkipEntraSetup) {
        Write-Host "=== Bootstrap phase 2/4: Entra service apps (skipped -SkipEntraSetup) ==="
    } else {
        Write-Host "=== Bootstrap phase 2/4: Entra internal service apps (D.2) ==="
        if (-not (Test-Path $entraSetupScript)) {
            Write-Error "entra_setup.ps1 not found at $entraSetupScript"
            exit 1
        }
        & $entraSetupScript -Environment $Environment
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

    Write-Host ""
    Write-Host "=== Bootstrap phase 3/4: migrate secrets to Key Vault ==="
    & "$PSScriptRoot/migrate-secrets.ps1" -Environment $Environment -SourceFile $SourceFile
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    Write-Host "=== Bootstrap phase 4/4: Container Apps ==="
    $deployOutput = Invoke-EnvDeployment `
        -EnvName $Environment `
        -ResourceGroupName $ResourceGroup `
        -ParametersFilePath $ParametersFile `
        -Tag $ImageTag `
        -IncludeContainerApps $true
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Show-EnvDeploymentOutputs -DeployOutput $deployOutput -EnvName $Environment
    exit 0
}

$includeApps = -not $InfrastructureOnly
$deployOutput = Invoke-EnvDeployment `
    -EnvName $Environment `
    -ResourceGroupName $ResourceGroup `
    -ParametersFilePath $ParametersFile `
    -Tag $ImageTag `
    -IncludeContainerApps $includeApps
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Show-EnvDeploymentOutputs -DeployOutput $deployOutput -EnvName $Environment
