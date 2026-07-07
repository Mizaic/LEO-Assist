# -- LEO AI Core - Secret Migration Script ---------------------------------
# Reads secrets from a .env file and pushes them to the environment Key Vault.
# Safe to re-run. Blank .env values skip overwrite when the secret already
# exists in Key Vault; otherwise a bootstrap placeholder is written so
# Container Apps deploy (Key Vault secret refs) can succeed.
#
# Usage:
#   .\infra\scripts\migrate-secrets.ps1 -Environment dev
#   .\infra\scripts\migrate-secrets.ps1 -Environment dev -VaultName kv-atlas-dev-4697
#   .\infra\scripts\migrate-secrets.ps1 -Environment dev -SourceFile secrets\.env
#   .\infra\scripts\migrate-secrets.ps1 -Environment dev -WhatIf
#
# Requires: az CLI logged in with Key Vault Secrets Officer on the target vault
# (vault is created by deploy.ps1 phase 1 or -InfrastructureOnly before first run).
param(
    [Parameter(Mandatory)]
    [ValidateSet('dev', 'val', 'prod')]
    [string]$Environment,

    [string]$VaultName = '',
    [string]$SourceFile = 'secrets\.env',
    [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function New-RandomHexSecret {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 32
    $rng.GetBytes($bytes)
    return [System.BitConverter]::ToString($bytes).Replace('-', '').ToLower()
}

function Test-KvSecretExists {
    param(
        [string]$VaultName,
        [string]$SecretName
    )

    az keyvault secret show `
        --vault-name $VaultName `
        --name $SecretName `
        --query id `
        --output tsv 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

function Get-PlaceholderSecretValue {
    param([string]$KvSecretName)

    if ($KvSecretName -match '-password$' -or $KvSecretName -match '-secret$') {
        return New-RandomHexSecret
    }
    if ($KvSecretName -eq 'redis-url') {
        return 'redis://placeholder-not-configured.invalid:6379'
    }
    if ($KvSecretName -match '-uri$') {
        return 'bolt://placeholder-not-configured.invalid:7687'
    }
    if ($KvSecretName -match '-(app-id|tenant-id|client-id)$') {
        return '00000000-0000-0000-0000-000000000000'
    }
    if ($KvSecretName -eq 'azure-service-bus-connection-string') {
        return 'Endpoint=sb://placeholder-not-configured.servicebus.windows.net/;SharedAccessKeyName=placeholder;SharedAccessKey=placeholder'
    }
    if ($KvSecretName -eq 'azure-openai-endpoint') {
        return 'https://placeholder-not-configured.openai.azure.com/'
    }
    if ($KvSecretName -match '^aws-(big|small|max)-model$') {
        return 'placeholder-model-not-configured'
    }
    if ($KvSecretName -eq 'aws-secret-access-key') {
        return New-RandomHexSecret
    }
    return 'placeholder-not-configured'
}

$KvName = if ($VaultName) { $VaultName } else { "mizaicai-$Environment-kv" }
Write-Host "  Target vault: $KvName"

# -- Secret name mapping: KV secret name -> env var in source file ---------
$SecretMap = [ordered]@{
    # Core infrastructure
    'neo4j-patient-uri'                  = 'NEO4J_URI'
    'neo4j-patient-password'             = 'NEO4J_PASSWORD'
    'neo4j-knowledge-uri'                = 'KNOWLEDGE_GRAPH_NEO4J_URI'
    'neo4j-knowledge-password'           = 'KNOWLEDGE_GRAPH_NEO4J_PASSWORD'
    'neo4j-guideline-uri'                = 'GUIDELINE_NEO4J_URI'
    'neo4j-guideline-password'           = 'GUIDELINE_NEO4J_PASSWORD'
    'redis-url'                          = 'REDIS_URL'
    # Azure
    'azure-ad-client-id'                 = 'AZURE_AD_CLIENT_ID'
    'azure-ad-client-secret'             = 'AZURE_AD_CLIENT_SECRET'
    'azure-ad-tenant-id'                 = 'AZURE_AD_TENANT_ID'
    'mail-graph-tenant-id'               = 'MAIL_GRAPH_TENANT_ID'
    'mail-graph-client-id'               = 'MAIL_GRAPH_CLIENT_ID'
    'mail-graph-client-secret'           = 'MAIL_GRAPH_CLIENT_SECRET'
    'azure-openai-api-key'               = 'AZURE_OPENAI_API_KEY'
    'azure-openai-endpoint'              = 'AZURE_OPENAI_ENDPOINT'
    'azure-service-bus-connection-string'= 'AZURE_SERVICE_BUS_CONNECTION_STRING'
    # AWS Bedrock
    'aws-access-key-id'                  = 'AWS_ACCESS_KEY_ID'
    'aws-secret-access-key'              = 'AWS_SECRET_ACCESS_KEY'
    'aws-big-model'                      = 'AWS_BIG_MODEL'
    'aws-small-model'                    = 'AWS_SMALL_MODEL'
    'aws-max-model'                      = 'AWS_MAX_MODEL'
    # Terminology & clinical APIs
    'snomed-api-key'                     = 'SNOMED_API_KEY'
    'umls-api-key'                       = 'UMLS_API_KEY'
    'nhs-trud-api-key'                   = 'NHS_TRUD_API_KEY'
    # Auth
    'auth-secret'                        = 'AUTH_SECRET'
    'service-auth-secret'                = 'SERVICE_AUTH_SECRET'
    # Inter-service app registrations
    'analytics-api-app-id'               = 'ANALYTICS_API_APP_ID'
    'fhir-api-app-id'                    = 'FHIR_API_APP_ID'
    'model-inference-app-id'             = 'MODEL_INFERENCE_APP_ID'
    'terminology-api-app-id'             = 'TERMINOLOGY_API_APP_ID'
    # NICE Syndication API + widget SDK
    'nice-api-key'                       = 'NICE_API_KEY'
    'sdk-host-shared-secret'             = 'SDK_HOST_SHARED_SECRET'
    'sdk-widget-token-secret'            = 'SDK_WIDGET_TOKEN_SECRET'
}

# -- Parse source .env file ------------------------------------------------
if (-not (Test-Path $SourceFile)) {
    Write-Error "Source file not found: $SourceFile"
    exit 1
}

$EnvVars = @{}
foreach ($line in Get-Content $SourceFile) {
    $trimmed = $line.Trim()
    if ($trimmed -eq '' -or $trimmed.StartsWith('#')) { continue }
    $eq = $trimmed.IndexOf('=')
    if ($eq -lt 1) { continue }
    $key = $trimmed.Substring(0, $eq).Trim()
    $val = $trimmed.Substring($eq + 1).Trim()
    $val = $val -replace '\s*#.*$', ''
    if ($val.StartsWith('"') -and $val.EndsWith('"')) { $val = $val.Substring(1, $val.Length - 2) }
    if ($val.StartsWith("'") -and $val.EndsWith("'")) { $val = $val.Substring(1, $val.Length - 2) }
    $EnvVars[$key] = $val
}

# Auto-generate AUTH_SECRET and SERVICE_AUTH_SECRET when absent from the source file.
foreach ($autoKey in @('AUTH_SECRET', 'SERVICE_AUTH_SECRET')) {
    if (-not $EnvVars.ContainsKey($autoKey) -or $EnvVars[$autoKey] -eq '') {
        Write-Host "$autoKey not found in source file -- generating a new one."
        $EnvVars[$autoKey] = New-RandomHexSecret
    }
}

# -- Push secrets to Key Vault ---------------------------------------------
$success = 0; $skipped = 0; $placeholders = 0; $errors = 0

foreach ($kvName2 in $SecretMap.Keys) {
    $envVar = $SecretMap[$kvName2]
    $value = $EnvVars[$envVar]
    $usedPlaceholder = $false

    if ([string]::IsNullOrWhiteSpace($value)) {
        if (Test-KvSecretExists -VaultName $KvName -SecretName $kvName2) {
            Write-Host "  SKIP  $kvName2 ($envVar is blank; already in Key Vault)"
            $skipped++
            continue
        }
        $value = Get-PlaceholderSecretValue -KvSecretName $kvName2
        $usedPlaceholder = $true
        Write-Host "  PLACEHOLDER  $kvName2 ($envVar is blank -- bootstrap value for deploy)"
    }

    if ($WhatIf) {
        $label = if ($usedPlaceholder) { 'WOULD SET PLACEHOLDER' } else { 'WOULD SET' }
        Write-Host "  $label  $kvName2 (from $envVar)"
        $success++
        if ($usedPlaceholder) { $placeholders++ }
        continue
    }

    $result = az keyvault secret set `
        --vault-name $KvName `
        --name $kvName2 `
        --value $value `
        --output none 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "  ERROR $kvName2 (exit $LASTEXITCODE): $result"
        $errors++
    } else {
        $label = if ($usedPlaceholder) { 'OK (placeholder)' } else { 'OK' }
        Write-Host "  $label    $kvName2"
        $success++
        if ($usedPlaceholder) { $placeholders++ }
    }
}

Write-Host ""
Write-Host "Done: $success set ($placeholders placeholders), $skipped skipped, $errors errors."
if ($placeholders -gt 0) {
    Write-Host "Replace placeholder secrets in Key Vault before production use."
}
if ($errors -gt 0) { exit 1 }
