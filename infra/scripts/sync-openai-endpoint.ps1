# -- Sync shared Azure OpenAI endpoint into env Bicep parameter files ------
# Usage:
#   .\infra\scripts\sync-openai-endpoint.ps1
#   .\infra\scripts\sync-openai-endpoint.ps1 -Endpoint 'https://mizaic-cds-oai.openai.azure.com/'
#
# Reads the deployed Cognitive Services endpoint (or uses -Endpoint) and sets
# azureOpenAiEndpoint in infra/bicep/parameters/{dev,val,prod}.bicepparam.
#
# Called automatically by deploy-openai.ps1 after the shared account deploy.
param(
    [string]$Endpoint = '',
    [string]$AccountName = 'mizaic-cds-oai',
    [string]$ResourceGroup = 'leo-prod-rg',
    [ValidateSet('dev', 'val', 'prod', 'all')]
    [string[]]$Environments = @('all'),
    [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Normalize-OpenAiEndpoint {
    param([string]$Url)
    $trimmed = $Url.Trim()
    if (-not $trimmed) {
        throw 'OpenAI endpoint URL is empty'
    }
    if ($trimmed -notmatch '^https://') {
        throw "OpenAI endpoint must be https:// (got: $trimmed)"
    }
    if (-not $trimmed.EndsWith('/')) {
        return "$trimmed/"
    }
    return $trimmed
}

function Get-DeployedOpenAiEndpoint {
    param(
        [string]$Name,
        [string]$Rg
    )
    $raw = az cognitiveservices account show `
        --name $Name `
        --resource-group $Rg `
        --query properties.endpoint `
        -o tsv
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) {
        throw "Could not read endpoint for $Name in $Rg. Run deploy-openai.ps1 first."
    }
    return Normalize-OpenAiEndpoint $raw
}

function Set-BicepStringParam {
    param(
        [string]$FilePath,
        [string]$ParamName,
        [string]$Value,
        [switch]$WhatIf
    )
    if (-not (Test-Path $FilePath)) {
        throw "Parameter file not found: $FilePath"
    }
    $content = Get-Content -Raw -Path $FilePath
    $pattern = "(?m)^param $([regex]::Escape($ParamName)) = '[^']*'(.*)$"
    if ($content -notmatch $pattern) {
        throw "Param $ParamName not found in $FilePath"
    }
    $suffix = $Matches[1]
    $line = "param $ParamName = '$Value'$suffix"
    $updated = [regex]::Replace($content, $pattern, $line, 1)
    if ($WhatIf) {
        Write-Host "WhatIf: $FilePath -> $ParamName = '$Value'"
        return
    }
    Set-Content -Path $FilePath -Value $updated -NoNewline
    Write-Host "Updated $FilePath ($ParamName)"
}

$endpointUrl = if ($Endpoint) {
    Normalize-OpenAiEndpoint $Endpoint
} else {
    Get-DeployedOpenAiEndpoint -Name $AccountName -Rg $ResourceGroup
}

$targetEnvs = if ($Environments -contains 'all') {
    @('dev', 'val', 'prod')
} else {
    $Environments
}

foreach ($envName in $targetEnvs) {
    $paramFile = "infra/bicep/parameters/$envName.bicepparam"
    Set-BicepStringParam -FilePath $paramFile -ParamName 'azureOpenAiEndpoint' -Value $endpointUrl -WhatIf:$WhatIf
}

Write-Host ""
Write-Host "Shared Azure OpenAI endpoint: $endpointUrl"
if (-not $WhatIf) {
    Write-Host ""
    Write-Host "Set AZURE_OPENAI_API_KEY in secrets\.env and run migrate-secrets.ps1 per environment."
    Write-Host "Optional: set AZURE_OPENAI_ENDPOINT=$endpointUrl in secrets\.env for local dev parity."
}
