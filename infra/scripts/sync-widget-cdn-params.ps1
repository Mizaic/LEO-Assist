# -- Sync widget CDN hostname into Bicep parameter files -------------------
# Usage:
#   .\infra\scripts\sync-widget-cdn-params.ps1 -Environment dev
#   .\infra\scripts\sync-widget-cdn-params.ps1 -Environment val -WebHost 'leoaiwidgetcdnval.z33.web.core.windows.net'
#
# Reads primaryEndpoints.web from the deployed widget storage account (or uses
# -WebHost) and updates infra/bicep/parameters/{env}.bicepparam:
#   widgetPublicHost, allowedOrigins (adds https://{host}, replaces prior widget origin)
#
# Called automatically by deploy-widget-cdn.ps1 after static website is enabled.
param(
    [Parameter(Mandatory)]
    [ValidateSet('dev', 'val', 'prod')]
    [string]$Environment,

    [string]$WebHost = '',
    [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-WidgetWebHost {
    param(
        [string]$EnvName,
        [string]$OverrideHost
    )
    if ($OverrideHost) {
        return $OverrideHost.Trim().TrimEnd('/')
    }
    $rg = "leo-widget-cdn-$EnvName"
    $account = "leoaiwidgetcdn$EnvName"
    $webUrl = az storage account show `
        --name $account `
        --resource-group $rg `
        --query primaryEndpoints.web `
        -o tsv
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($webUrl)) {
        throw "Could not read primaryEndpoints.web for $account in $rg. Deploy widget CDN first."
    }
    return ($webUrl -replace '^https?://', '').TrimEnd('/')
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

function Merge-WidgetOriginIntoAllowedOrigins {
    param(
        [string]$FilePath,
        [string]$EnvName,
        [string]$WidgetHost,
        [switch]$WhatIf
    )
    $content = Get-Content -Raw -Path $FilePath
    $pattern = "(?m)^param allowedOrigins = '([^']*)'(.*)$"
    if ($content -notmatch $pattern) {
        throw "Param allowedOrigins not found in $FilePath"
    }
    $suffix = $Matches[2]
    $widgetOrigin = "https://$WidgetHost"
    $origins = $Matches[1] -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    $widgetPattern = "^https://leoaiwidgetcdn$([regex]::Escape($EnvName))\."
    $kept = @($origins | Where-Object { $_ -notmatch $widgetPattern })
    if ($kept -notcontains $widgetOrigin) {
        $kept += $widgetOrigin
    }
    $merged = $kept -join ','
    $line = "param allowedOrigins = '$merged'$suffix"
    $updated = [regex]::Replace($content, $pattern, $line, 1)
    if ($WhatIf) {
        Write-Host "WhatIf: $FilePath -> allowedOrigins includes $widgetOrigin"
        return
    }
    Set-Content -Path $FilePath -Value $updated -NoNewline
    Write-Host "Updated $FilePath (allowedOrigins)"
}

$hostName = Get-WidgetWebHost -EnvName $Environment -OverrideHost $WebHost
$widgetParams = "infra/widget-cdn/parameters/$Environment.bicepparam"
$mainParams = "infra/bicep/parameters/$Environment.bicepparam"

Set-BicepStringParam -FilePath $mainParams -ParamName 'widgetPublicHost' -Value $hostName -WhatIf:$WhatIf
Merge-WidgetOriginIntoAllowedOrigins -FilePath $mainParams -EnvName $Environment -WidgetHost $hostName -WhatIf:$WhatIf

Write-Host ""
Write-Host "Widget CDN hostname: $hostName"
Write-Host "  https://$hostName/v1/leo-widget.js"
if (-not $WhatIf) {
    Write-Host ""
    Write-Host "Set GitHub secret WIDGET_PUBLIC_HOST to the same hostname before widget-release.yml."
}
