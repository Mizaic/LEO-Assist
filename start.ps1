# Primary Care Audit - Local Development Startup Script
# Usage: .\start.ps1 [-Service <name>] [-InfraOnly]

param(
    [string]$Service = "",
    [switch]$InfraOnly
)

$ErrorActionPreference = "Stop"

Write-Host "Primary Care Audit - Local Development" -ForegroundColor Cyan

if (-not (Test-Path ".env")) {
    Write-Host "No .env file found. Copying from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env - please review and update credentials." -ForegroundColor Yellow
}

if ($InfraOnly) {
    Write-Host "Starting infrastructure only (Neo4j Patient, Neo4j Knowledge, Redis)..." -ForegroundColor Green
    docker compose up -d neo4j-patient neo4j-knowledge redis
    Write-Host "Infrastructure started. Ports:" -ForegroundColor Green
    Write-Host "  Neo4j Patient:   http://localhost:7474 (bolt://localhost:7687)" -ForegroundColor White
    Write-Host "  Neo4j Knowledge: http://localhost:7475 (bolt://localhost:7688)" -ForegroundColor White
    Write-Host "  Redis:           localhost:6379" -ForegroundColor White
    exit 0
}

if ($Service) {
    Write-Host "Starting service: $Service (with infrastructure)..." -ForegroundColor Green
    docker compose up -d neo4j-patient neo4j-knowledge redis
    docker compose up -d $Service
    exit 0
}

Write-Host "Starting all services..." -ForegroundColor Green
docker compose up -d
Write-Host ""
Write-Host "Services:" -ForegroundColor Green
Write-Host "  Core API:        http://localhost:8000" -ForegroundColor White
Write-Host "  Terminology API: http://localhost:8001" -ForegroundColor White
Write-Host "  FHIR API:        http://localhost:8002" -ForegroundColor White
Write-Host "  Analytics API:   http://localhost:8003" -ForegroundColor White
Write-Host "  UI:              http://localhost:3000" -ForegroundColor White
Write-Host ""
Write-Host "Infrastructure:" -ForegroundColor Green
Write-Host "  Neo4j Patient:   http://localhost:7474" -ForegroundColor White
Write-Host "  Neo4j Knowledge: http://localhost:7475" -ForegroundColor White
Write-Host "  Redis:           localhost:6379" -ForegroundColor White
