param(
    [int]$ApiPort = 8000,
    [int]$UiPort = 3000
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiVenvPython = Join-Path $RepoRoot ".venv/Scripts/python.exe"
$ApiAppDir = Join-Path $RepoRoot "services/api"
$UiDir = Join-Path $RepoRoot "services/ui"

if (-not (Test-Path $ApiVenvPython)) {
    throw "Backend venv not found at: $ApiVenvPython"
}
if (-not (Test-Path (Join-Path $UiDir "node_modules"))) {
    throw "Frontend dependencies not found. Run 'npm install' in services/ui/"
}

$backendCmd = "Set-Location -LiteralPath `"$RepoRoot`"; & `"$ApiVenvPython`" -m uvicorn app.main:app --app-dir `"$ApiAppDir`" --reload --host 0.0.0.0 --port $ApiPort"
$frontendCmd = "Set-Location -LiteralPath `"$UiDir`"; npm.cmd run dev -- --port $UiPort"

Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoExit",
    "-Command",
    $backendCmd
) -WorkingDirectory $RepoRoot | Out-Null

Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoExit",
    "-Command",
    $frontendCmd
) -WorkingDirectory $UiDir | Out-Null

Write-Host "Started backend on http://localhost:$ApiPort"
Write-Host "Started frontend on http://localhost:$UiPort (Next.js)"
Write-Host "Two new PowerShell windows were opened."
