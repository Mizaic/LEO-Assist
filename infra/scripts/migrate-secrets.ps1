# -- LEO AI Core - Secret Migration Script ---------------------------------
# Reads secrets from a .env file and pushes them to the environment Key Vault.
# Safe to re-run: only overwrites if the value has changed.
#
# Usage:
#   .\infra\scripts\migrate-secrets.ps1 -Environment dev
#   .\infra\scripts\migrate-secrets.ps1 -Environment dev -VaultName kv-atlas-dev-4697
#   .\infra\scripts\migrate-secrets.ps1 -Environment dev -SourceFile secrets\.env
#   .\infra\scripts\migrate-secrets.ps1 -Environment dev -WhatIf
#
# Requires: az CLI logged in with Key Vault Secrets Officer on the target vault
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

$KvName = if ($VaultName) { $VaultName } else { "leoai-$Environment-kv" }
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
    'azure-openai-api-key'               = 'AZURE_OPENAI_API_KEY'
    'azure-openai-endpoint'              = 'AZURE_OPENAI_ENDPOINT'
    'azure-storage-connection-string'    = 'AZURE_STORAGE_CONNECTION_STRING'
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

# -- If SERVICE_AUTH_SECRET not in source file, generate one ---------------
if (-not $EnvVars.ContainsKey('SERVICE_AUTH_SECRET') -or $EnvVars['SERVICE_AUTH_SECRET'] -eq '') {
    Write-Host "SERVICE_AUTH_SECRET not found in source file -- generating a new one."
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 32
    $rng.GetBytes($bytes)
    $EnvVars['SERVICE_AUTH_SECRET'] = [System.BitConverter]::ToString($bytes).Replace('-', '').ToLower()
}

# -- Push secrets to Key Vault ---------------------------------------------
$success = 0; $skipped = 0; $errors = 0

foreach ($kvName2 in $SecretMap.Keys) {
    $envVar = $SecretMap[$kvName2]
    $value = $EnvVars[$envVar]

    if ([string]::IsNullOrWhiteSpace($value)) {
        Write-Host "  SKIP  $kvName2 ($envVar is blank)"
        $skipped++
        continue
    }

    if ($WhatIf) {
        Write-Host "  WOULD SET  $kvName2 (from $envVar)"
        $success++
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
        Write-Host "  OK    $kvName2"
        $success++
    }
}

Write-Host ""
Write-Host "Done: $success set, $skipped skipped, $errors errors."
if ($errors -gt 0) { exit 1 }
