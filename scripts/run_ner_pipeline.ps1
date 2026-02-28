# NER training-set pipeline runner.
#
# Each run gets its own isolated output folder under exports/ner/runs/<RunId>.
# A separate merge step deduplicates across all runs into exports/ner/all_domains/.
# QA, adapters, and manifest always operate on the merged all_domains output.
#
# Usage (from repo root):
#   .\scripts\run_ner_pipeline.ps1                          # full pipeline, new run
#   .\scripts\run_ner_pipeline.ps1 -Step mine               # mine only (new run)
#   .\scripts\run_ner_pipeline.ps1 -Step merge              # merge all runs -> all_domains
#   .\scripts\run_ner_pipeline.ps1 -Step qa                 # qa + seed on all_domains
#   .\scripts\run_ner_pipeline.ps1 -Step adapters           # spaCy training adapters
#   .\scripts\run_ner_pipeline.ps1 -Step manifest           # publish manifest.json
#   .\scripts\run_ner_pipeline.ps1 -MaxEncounters 200       # quick test run
#   .\scripts\run_ner_pipeline.ps1 -SkipResolve             # skip terminology API
#   .\scripts\run_ner_pipeline.ps1 -RunId my_label          # explicit run ID
#   .\scripts\run_ner_pipeline.ps1 -RunDir exports\ner\runs\20260228_160000  # resume specific run

param(
    [ValidateSet('all','mine','merge','qa','adapters','manifest')]
    [string]$Step          = 'all',
    [switch]$SkipResolve,
    [int]$MaxEncounters    = 0,
    [string]$RunId         = '',
    [string]$RunDir        = '',
    [string]$MergedDir     = 'exports\ner\all_domains',
    [string]$RunsDir       = 'exports\ner\runs'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPy   = Join-Path $RepoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $VenvPy)) {
    Write-Error "  .venv not found at $VenvPy - run .\scripts\start_primary_care.ps1 first."
    exit 1
}

$VenvVer = & $VenvPy --version 2>&1
Write-Host ''
Write-Host '  NER Pipeline Runner' -ForegroundColor Cyan
Write-Host "  Python  : $VenvVer" -ForegroundColor DarkGray
Write-Host "  Step    : $Step" -ForegroundColor DarkGray

# Load secrets
$masterEnv = Join-Path $RepoRoot 'secrets\.env'
if (Test-Path $masterEnv) {
    $n = 0
    Get-Content $masterEnv | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#')) {
            $eqIdx = $line.IndexOf('=')
            if ($eqIdx -gt 0) {
                $key = $line.Substring(0, $eqIdx).Trim()
                $val = $line.Substring($eqIdx + 1)
                if ($val -match '^(.*?)\s{2,}#') { $val = $Matches[1] }
                $val = $val.Trim()
                [System.Environment]::SetEnvironmentVariable($key, $val, 'Process')
                $n++
            }
        }
    }
    Write-Host "  Secrets : $n vars loaded from secrets\.env" -ForegroundColor Green
}
$env:PYTHONPATH = $RepoRoot

# Resolve run directory
if ($RunDir -ne '') {
    $ResolvedRunDir = $RunDir
} elseif ($RunId -ne '') {
    $ResolvedRunDir = Join-Path $RunsDir $RunId
} else {
    $ts = Get-Date -Format 'yyyyMMdd_HHmmss'
    $ResolvedRunDir = Join-Path $RunsDir $ts
    $RunId = $ts
}
Write-Host "  Run dir : $ResolvedRunDir" -ForegroundColor DarkGray
Write-Host "  Merged  : $MergedDir" -ForegroundColor DarkGray
Write-Host ''

function Run-Step {
    param([string]$Label, [string[]]$PyArgs)
    Write-Host "  [$Label]" -ForegroundColor Yellow
    & $VenvPy @PyArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "  [$Label] FAILED (exit $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
    Write-Host "  [$Label] done" -ForegroundColor Green
    Write-Host ''
}

# Step: mine -> isolated run folder
if ($Step -eq 'all' -or $Step -eq 'mine') {
    $mineArgs = @(
        'scripts\mine_all_domains.py',
        '--run-dir', $ResolvedRunDir
    )
    if ($SkipResolve)         { $mineArgs += '--skip-resolve' }
    if ($MaxEncounters -gt 0) { $mineArgs += @('--max-encounters', "$MaxEncounters") }
    Run-Step 'mine' $mineArgs
}

# Step: merge all runs -> all_domains
if ($Step -eq 'all' -or $Step -eq 'merge') {
    Run-Step 'merge' @(
        'scripts\merge_ner_runs.py',
        '--runs-dir', $RunsDir,
        '--out-dir',  $MergedDir
    )
}

# Step: qa + seed integration on merged output
if ($Step -eq 'all' -or $Step -eq 'qa') {
    Run-Step 'qa' @(
        'scripts\qa_all_domains_ner.py',
        '--out-dir', $MergedDir
    )
}

# Step: spaCy training adapters
if ($Step -eq 'all' -or $Step -eq 'adapters') {
    Run-Step 'adapters' @(
        'scripts\export_training_adapters.py',
        '--out-dir', "$MergedDir\training_adapters"
    )
}

# Step: publish manifest
if ($Step -eq 'all' -or $Step -eq 'manifest') {
    Run-Step 'manifest' @(
        'scripts\publish_dataset_manifest.py',
        '--out-dir', $MergedDir
    )
}

Write-Host "  Pipeline complete." -ForegroundColor Cyan
Write-Host "  Run output : $ResolvedRunDir" -ForegroundColor DarkGray
Write-Host "  Merged     : $MergedDir" -ForegroundColor DarkGray
Write-Host ''
