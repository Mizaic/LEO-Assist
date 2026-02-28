# Primary Care Audit - Local Development Startup
# Creates / activates .venv, installs all deps, starts every microservice.
#
# Usage:
#   .\scripts\start_primary_care.ps1                            # full stack (3 coding + 2 analysis workers)
#   .\scripts\start_primary_care.ps1 -SkipInstall               # skip pip/npm
#   .\scripts\start_primary_care.ps1 -NoWorkers                 # skip background workers
#   .\scripts\start_primary_care.ps1 -Services api,ui           # named subset
#   .\scripts\start_primary_care.ps1 -CodingWorkers 1           # single coding worker (debug)
#   .\scripts\start_primary_care.ps1 -AnalysisWorkers 1         # single analysis worker (debug)
#   .\scripts\start_primary_care.ps1 -ModelInference            # also start NER model inference service
#   .\scripts\start_primary_care.ps1 -TrainingWorker            # also start NER training worker (port 8005)
#
# Model inference service notes:
#   Only needed when CODING_EXTRACTOR_BACKEND=model|auto (default: llm).
#   Downloads the active NER model artifact from Azure Blob at startup.
#   Exposes /extract, /health, /reload, /versions on -ModelInferencePort (default 8004).
#
# Training worker notes:
#   On-demand — start when you want to fine-tune the NER model.
#   Reads TrainingLabel nodes from Neo4j, trains NER head on Bio_ClinicalBERT, uploads to blob.
#   Exposes /train/jobs, /train/progress/{job_id} on -TrainingWorkerPort (default 8005).

param(
    [int]$ApiPort             = 8000,
    [int]$TermPort            = 8001,
    [int]$FhirPort            = 8002,
    [int]$AnalyticsPort       = 8003,
    [int]$ModelInferencePort  = 8004,
    [int]$TrainingWorkerPort  = 8005,
    [int]$UiPort              = 3000,
    [int]$CodingWorkers       = 3,
    [int]$AnalysisWorkers     = 2,
    [switch]$SkipInstall,
    [switch]$NoWorkers,
    [switch]$ModelInference,
    [switch]$TrainingWorker,
    [string[]]$Services       = @()
)

$ErrorActionPreference = "Stop"

$RepoRoot           = Split-Path -Parent $PSScriptRoot
$VenvDir            = Join-Path $RepoRoot ".venv"
$VenvPython         = Join-Path $VenvDir  "Scripts\python.exe"
# $VenvPip            = Join-Path $VenvDir  "Scripts\pip.exe"
$UiDir              = Join-Path $RepoRoot "services\ui"
$ApiDir             = Join-Path $RepoRoot "services\api"
$ModelInferenceDir  = Join-Path $RepoRoot "services\model_inference"
$TrainingWorkerDir  = Join-Path $RepoRoot "services\training_worker"
$ReqFile            = Join-Path $RepoRoot "requirements.txt"
$ModelInferenceReq  = Join-Path $ModelInferenceDir "requirements.txt"
$TrainingWorkerReq  = Join-Path $TrainingWorkerDir "requirements.txt"
$ModelCacheDir      = Join-Path $RepoRoot ".model_cache"

Write-Host ""
Write-Host "  Primary Care Audit - Local Dev Startup" -ForegroundColor Cyan
Write-Host ""

# -- Secrets ---------------------------------------------------------------
# Secrets live in secrets\.env (migrating to Key Vault).
# Parsed into process env vars so child windows inherit them - never copied.
$masterEnv = Join-Path $RepoRoot "secrets\.env"
if (Test-Path $masterEnv) {
    $secretCount = 0
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
                $secretCount++
            }
        }
    }
    Write-Host "  [env]  Loaded $secretCount vars from secrets\.env (in-memory only)" -ForegroundColor Green
} else {
    Write-Host "  [env]  secrets\.env not found - services may fail without credentials." -ForegroundColor Yellow
    Write-Host "         Create secrets\.env or set environment variables manually." -ForegroundColor Yellow
}

# -- Local model cache directory -------------------------------------------
# Model inference service downloads NER artifacts from Azure Blob into this dir.
# Committed to .gitignore; safe to delete between dev sessions.
if (-not (Test-Path $ModelCacheDir)) {
    New-Item -ItemType Directory -Path $ModelCacheDir | Out-Null
    Write-Host "  [dir]  Created .model_cache/ for NER model artifacts." -ForegroundColor Green
}

# -- Python virtual environment --------------------------------------------
if (-not (Test-Path $VenvPython)) {
    Write-Host "  [venv] Creating virtual environment..." -ForegroundColor Yellow
    python -m venv $VenvDir
    Write-Host "  [venv] .venv created." -ForegroundColor Green
}

# -- Python dependencies ---------------------------------------------------
if (-not $SkipInstall) {
    Write-Host "  [pip]  Installing / upgrading Python dependencies..." -ForegroundColor Yellow
    & $VenvPython -m pip install --quiet --upgrade pip
    & $VenvPython -m pip install --quiet --upgrade -r $ReqFile
    # Model inference service has its own requirements (spaCy, azure-storage-blob)
    # that may drift from the monorepo floor - install on top of the venv.
    if (Test-Path $ModelInferenceReq) {
        & $VenvPython -m pip install --quiet --upgrade -r $ModelInferenceReq
    }
    if ($TrainingWorker -and (Test-Path $TrainingWorkerReq)) {
        & $VenvPython -m pip install --quiet --upgrade -r $TrainingWorkerReq
    }
    Write-Host "  [pip]  Python dependencies up to date." -ForegroundColor Green
}

# -- Node dependencies -----------------------------------------------------
if (-not $SkipInstall) {
    Write-Host "  [npm]  Installing / updating UI dependencies..." -ForegroundColor Yellow
    Push-Location $UiDir
    npm.cmd install --silent
    Pop-Location
    Write-Host "  [npm]  UI dependencies up to date." -ForegroundColor Green
} elseif (-not (Test-Path (Join-Path $UiDir "node_modules"))) {
    Write-Host "  [npm]  node_modules missing - running npm install..." -ForegroundColor Yellow
    Push-Location $UiDir
    npm.cmd install --silent
    Pop-Location
    Write-Host "  [npm]  UI dependencies installed." -ForegroundColor Green
}

# -- Helpers ---------------------------------------------------------------

function ShouldStart([string]$Name) {
    if ($Services.Count -eq 0) { return $true }
    return $Services -contains $Name
}

function Start-ServiceWindow {
    param(
        [string]$Title,
        [string]$Command,
        [string]$WorkDir = $RepoRoot
    )
    $preamble = "Set-Location -LiteralPath '$WorkDir'; `$env:PYTHONPATH = '$RepoRoot'"
    $titleCmd = "`$Host.UI.RawUI.WindowTitle = '$Title'"
    $fullCmd  = "$titleCmd; $preamble; $Command"
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", $fullCmd -WorkingDirectory $WorkDir | Out-Null
}

# -- Start services --------------------------------------------------------
$windowCount = 0

Write-Host ""
Write-Host "  Starting services..." -ForegroundColor Green

# 1  Core API  (services/api)  ->  :8000
if (ShouldStart "api") {
    Start-ServiceWindow -Title "Core API :$ApiPort" -Command "& '$VenvPython' -m uvicorn app.main:app --app-dir '$ApiDir' --reload --host 0.0.0.0 --port $ApiPort"
    Write-Host "    Core API           http://localhost:$ApiPort" -ForegroundColor White
    $windowCount++
}

# 2  Terminology API  (services/terminology_api)  ->  :8001
if (ShouldStart "terminology_api") {
    Start-ServiceWindow -Title "Terminology API :$TermPort" -Command "& '$VenvPython' -m uvicorn services.terminology_api.app.main:app --reload --host 0.0.0.0 --port $TermPort"
    Write-Host "    Terminology API    http://localhost:$TermPort" -ForegroundColor White
    $windowCount++
}

# 3  FHIR API  (services/fhir_api)  ->  :8002
if (ShouldStart "fhir_api") {
    Start-ServiceWindow -Title "FHIR API :$FhirPort" -Command "& '$VenvPython' -m uvicorn services.fhir_api.app.main:app --reload --host 0.0.0.0 --port $FhirPort"
    Write-Host "    FHIR API           http://localhost:$FhirPort" -ForegroundColor White
    $windowCount++
}

# 4  Analytics API  (services/analytics_api)  ->  :8003
if (ShouldStart "analytics_api") {
    Start-ServiceWindow -Title "Analytics API :$AnalyticsPort" -Command "& '$VenvPython' -m uvicorn services.analytics_api.app.main:app --reload --host 0.0.0.0 --port $AnalyticsPort"
    Write-Host "    Analytics API      http://localhost:$AnalyticsPort" -ForegroundColor White
    $windowCount++
}

# 5  Model Inference Service  (NER spaCy endpoint; only when -ModelInference or CODING_EXTRACTOR_BACKEND=model|auto)
#    Downloads the active model from Azure Blob at startup. Hot-reload via /reload.
#    Skipped by default because CODING_EXTRACTOR_BACKEND defaults to 'llm'.
$needsModelInference = $ModelInference -or ($env:CODING_EXTRACTOR_BACKEND -in @("model", "auto"))
if ($needsModelInference -and (ShouldStart "model_inference")) {
    $miCmd = "& '$VenvPython' -m uvicorn app.main:app --app-dir '$ModelInferenceDir' --host 0.0.0.0 --port $ModelInferencePort"
    Start-ServiceWindow -Title "Model Inference :$ModelInferencePort" -Command $miCmd -WorkDir $RepoRoot
    Write-Host "    Model Inference    http://localhost:$ModelInferencePort  (NER /extract /health /reload /versions)" -ForegroundColor White
    $windowCount++
} elseif (-not $needsModelInference) {
    Write-Host "    Model Inference    [skipped - CODING_EXTRACTOR_BACKEND=llm; use -ModelInference to start]" -ForegroundColor DarkGray
}

# 6  Training Worker  (NER fine-tuning; only when -TrainingWorker flag)
#    Starts in external PowerShell window like other services. Kills any existing process on port first.
if ($TrainingWorker -and (ShouldStart "training_worker")) {
    $existing = Get-NetTCPConnection -LocalPort $TrainingWorkerPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($existing) {
        $procId = $existing.OwningProcess
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Write-Host "    Training Worker    [killed existing PID $procId]" -ForegroundColor Yellow
        Start-Sleep -Seconds 2
    }
    $twCmd = "& '$VenvPython' -m uvicorn app.main:app --app-dir '$TrainingWorkerDir' --host 0.0.0.0 --port $TrainingWorkerPort"
    Start-ServiceWindow -Title "Training Worker :$TrainingWorkerPort" -Command $twCmd -WorkDir $RepoRoot
    Write-Host "    Training Worker    http://localhost:$TrainingWorkerPort  (NER fine-tuning /train/jobs /train/progress)" -ForegroundColor White
    $windowCount++
} else {
    Write-Host "    Training Worker    [skipped; use -TrainingWorker to start]" -ForegroundColor DarkGray
}

# 6  Coding Workers  (message-bus consumers, fan-out parallel classification + extraction)
if (-not $NoWorkers -and (ShouldStart "coding_worker")) {
    for ($i = 1; $i -le $CodingWorkers; $i++) {
        Start-ServiceWindow -Title "Coding Worker $i" -Command "& '$VenvPython' -m services.coding_worker.app.main"
    }
    Write-Host "    Coding Workers     (x$CodingWorkers - message bus listeners, fan-out mode)" -ForegroundColor White
    $windowCount += $CodingWorkers
}

# 7  Analysis Workers  (message-bus consumers, one per patient, sequential stages)
if (-not $NoWorkers -and (ShouldStart "analysis_worker")) {
    for ($i = 1; $i -le $AnalysisWorkers; $i++) {
        Start-ServiceWindow -Title "Analysis Worker $i" -Command "& '$VenvPython' -m services.analysis_worker.app.main"
    }
    Write-Host "    Analysis Workers   (x$AnalysisWorkers - message bus listeners)" -ForegroundColor White
    $windowCount += $AnalysisWorkers
}

# 8  UI  (Next.js)  ->  :3000
if (ShouldStart "ui") {
    Start-ServiceWindow -Title "UI :$UiPort" -Command "npm.cmd run dev -- --port $UiPort" -WorkDir $UiDir
    Write-Host "    UI                 http://localhost:$UiPort" -ForegroundColor White
    $windowCount++
}

# -- Summary ---------------------------------------------------------------
Write-Host ""
Write-Host "  $windowCount PowerShell window(s) opened. Close them to stop services." -ForegroundColor DarkGray
Write-Host ""
