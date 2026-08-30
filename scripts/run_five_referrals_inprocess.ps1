# Run five referrals through the in-process pipeline, one after another.
#
# Each referral is processed inside this Python process (no Azure Service Bus,
# no separate worker). --reset clears prior facts and draft assessments first.
# Timeout is 1200 seconds per referral. Failed referrals do not stop the rest.
#
# Usage (from repo root):
#   .\scripts\run_five_referrals_inprocess.ps1
#   .\scripts\run_five_referrals_inprocess.ps1 -Neo4jNote 98dd482b
#
# Log file: $env:TEMP\leo-five\run.log  (Windows equivalent of /tmp/leo-five)

param(
    [string[]]$ReferralIds = @(
        '000481914514',
        '000481827411',
        '000481858094',
        '000481858468',
        '000481888499'
    ),
    [string]$Neo4jNote = '98dd482b',
    [switch]$NoReset,
    [int]$TimeoutSeconds = 1200
)

$ErrorActionPreference = 'Stop'
# Python logs (Neo4j driver, etc.) go to stderr. Do not treat that as a
# terminating error, or the first log line aborts the batch.
$PSNativeCommandUseErrorActionPreference = $false
$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPy = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$Runner = Join-Path $RepoRoot 'scripts\run_referral_inprocess.py'

if (-not (Test-Path $VenvPy)) {
    Write-Error ".venv not found at $VenvPy"
    exit 1
}
if (-not (Test-Path $Runner)) {
    Write-Error "Runner not found at $Runner"
    exit 1
}

function Get-UtcStamp {
    return (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
}

$LogDir = Join-Path $env:TEMP 'leo-five'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir 'run.log'

$ResetArgs = @()
$ResetNote = 'no'
if (-not $NoReset) {
    $ResetArgs = @('--reset')
    $ResetNote = 'yes'
}

Set-Location $RepoRoot
Set-Content -Path $LogFile -Value ''

function Write-RunLog {
    param([string]$Message)
    # Write-Host (not Tee-Object): function output must stay a single exit code.
    Add-Content -Path $LogFile -Value $Message
    Write-Host $Message
}

function Invoke-ReferralPython {
    param([string]$ReferralId)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $VenvPy $Runner --referral-id $ReferralId @ResetArgs --timeout $TimeoutSeconds 2>&1
        $code = $LASTEXITCODE
        foreach ($line in @($output)) {
            Write-RunLog -Message ([string]$line)
        }
        if ($null -eq $code) {
            return 1
        }
        return [int]$code
    } finally {
        $ErrorActionPreference = $prev
    }
}

Write-RunLog "five-patient in-process run started $(Get-UtcStamp)"
Write-RunLog "neo4j=$Neo4jNote reset=$ResetNote"
Write-RunLog ""

foreach ($rid in $ReferralIds) {
    Write-RunLog "============================================================"
    Write-RunLog "START $rid $(Get-UtcStamp)"
    Write-RunLog "============================================================"
    $code = Invoke-ReferralPython -ReferralId $rid
    Write-RunLog "END $rid exit=$code $(Get-UtcStamp)"
    Write-RunLog ""
}

Write-RunLog "ALL DONE $(Get-UtcStamp)"
Write-Host ""
Write-Host "Log saved to $LogFile"
