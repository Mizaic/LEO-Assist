# -- LEO AI Core - local build, ACR push, Container Apps deploy (no GitHub Actions) --
#
# Prerequisites:
#   - Docker Desktop (or Docker engine) running
#   - Azure CLI: az login, and rights to ACR push + Container Apps update
#   - Git (optional): used for image tag sha-<full-commit>; else use -ImageTag
#   - Root .dockerignore must exclude node_modules/.next/.git etc. (build context from repo root)
#
# Usage (from repo root):
#   .\infra\scripts\build-push-deploy-local.ps1
#   .\infra\scripts\build-push-deploy-local.ps1 -ResourceGroup leo-ai-dev -ImageTag sha-abc123def
#   .\infra\scripts\build-push-deploy-local.ps1 -SkipDeploy
#   .\infra\scripts\build-push-deploy-local.ps1 -SkipTests
#
param(
    [string]$ResourceGroup = "leo-ai-dev",
    [string]$AcrName = "leoaicr",
    [string]$ImageTag = "",
    [string]$SubscriptionId = "",
    [switch]$SkipDeploy,
    [switch]$SkipPush,
    [switch]$SkipBuild,
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
Set-Location $RepoRoot

if ($SubscriptionId) {
    Write-Host "Setting subscription $SubscriptionId"
    az account set --subscription $SubscriptionId
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not $ImageTag) {
    try {
        $sha = (& git rev-parse HEAD 2>$null).Trim()
        if ($sha) { $ImageTag = "sha-$sha" }
    } catch { }
    if (-not $ImageTag) {
        $ImageTag = "local-$(Get-Date -Format 'yyyyMMddHHmmss')"
        Write-Warning "Git not available; using tag $ImageTag"
    } else {
        Write-Host "Image tag from git: $ImageTag"
    }
} else {
    Write-Host "Using image tag: $ImageTag"
}

$AcrLoginServer = "$AcrName.azurecr.io"

$Services = @(
    @{ Name = "core-api";       Dockerfile = "infra/dockerfiles/Dockerfile.core-api" },
    @{ Name = "terminology-api"; Dockerfile = "infra/dockerfiles/Dockerfile.terminology-api" },
    @{ Name = "fhir-api";       Dockerfile = "infra/dockerfiles/Dockerfile.fhir-api" },
    @{ Name = "analytics-api";  Dockerfile = "infra/dockerfiles/Dockerfile.analytics-api" },
    @{ Name = "pipeline-worker"; Dockerfile = "infra/dockerfiles/Dockerfile.pipeline-worker" },
    @{ Name = "model-inference"; Dockerfile = "infra/dockerfiles/Dockerfile.model-inference" },
    @{ Name = "training-worker"; Dockerfile = "infra/dockerfiles/Dockerfile.training-worker" },
    @{ Name = "ui";             Dockerfile = "infra/dockerfiles/Dockerfile.ui" }
)

$ContainerApps = @(
    "core-api", "terminology-api", "fhir-api", "analytics-api",
    "model-inference", "training-worker", "pipeline-worker", "ui"
)

function Assert-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

Assert-Command "az"
Assert-Command "docker"

if (-not $SkipTests) {
    Write-Host "`n-- pytest (repo root) --"
    Assert-Command "python"
    python -m pip install -q -r requirements.txt 2>$null
    pip install -q pytest pytest-asyncio 2>$null
    $env:PYTHONPATH = $RepoRoot
    python -m pytest tests/ -v --tb=short
    if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
}

if (-not $SkipBuild) {
    Write-Host "`n-- docker build --"
    foreach ($s in $Services) {
        $image = "$AcrLoginServer/$($s.Name)"
        $df = $s.Dockerfile
        Write-Host "Building $image ($df) ..."
        docker build `
            --file $df `
            --tag "${image}:$ImageTag" `
            --tag "${image}:latest" `
            .
        if ($LASTEXITCODE -ne 0) { throw "docker build failed for $($s.Name)" }
    }
}

if (-not $SkipPush) {
    Write-Host "`n-- az acr login --"
    az acr login --name $AcrName
    if ($LASTEXITCODE -ne 0) { throw "az acr login failed" }

    Write-Host "`n-- docker push --"
    foreach ($s in $Services) {
        $image = "$AcrLoginServer/$($s.Name)"
        docker push "${image}:$ImageTag"
        if ($LASTEXITCODE -ne 0) { throw "docker push failed for $($s.Name) ($ImageTag)" }
        docker push "${image}:latest"
        if ($LASTEXITCODE -ne 0) { throw "docker push failed for $($s.Name) (latest)" }
    }
}

if (-not $SkipDeploy) {
    Write-Host "`n-- az containerapp update --"
    foreach ($app in $ContainerApps) {
        $fullImage = "$AcrLoginServer/${app}:$ImageTag"
        Write-Host "Updating $app -> $fullImage"
        az containerapp update `
            --name $app `
            --resource-group $ResourceGroup `
            --image $fullImage `
            --output none
        if ($LASTEXITCODE -ne 0) { throw "containerapp update failed for $app" }
    }
    Write-Host "`nDeploy complete. Tag: $ImageTag  RG: $ResourceGroup"
} else {
    Write-Host "`nSkipDeploy: images are in ACR as ${AcrLoginServer}/<service>:$ImageTag"
}
