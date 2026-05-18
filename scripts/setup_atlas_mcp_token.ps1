# setup_atlas_mcp_token.ps1
# Legacy Atlas bearer-token helper.
#
# The active Cursor MCP configuration uses https://atlas-mcp.healthcarecopilot.ai/mcp
# with X-MCP-Api-Key. This script is disabled by default because the old
# device-code flow rewrites ~/.cursor/mcp.json back to the deprecated
# https://atlas.healthcarecopilot.ai/mcp bearer-token endpoint.
#
# Usage:
#   .\scripts\setup_atlas_mcp_token.ps1
#     Prints the current API-key MCP guidance and exits without changing files.
#
# Legacy bearer-token flow, only if deliberately needed:
#   .\scripts\setup_atlas_mcp_token.ps1 -LegacyBearerAuth
#   .\scripts\setup_atlas_mcp_token.ps1 -Refresh -LegacyBearerAuth

param(
    [switch]$Refresh,
    [switch]$LegacyBearerAuth
)

$ErrorActionPreference = "Stop"

$BASE_URL   = "https://atlas.healthcarecopilot.ai"
$MCP_CONFIG = "$env:USERPROFILE\.cursor\mcp.json"
$TOKEN_FILE = "$env:USERPROFILE\.cursor\atlas_refresh_token.txt"
$POLL_SECS  = 10
$MAX_WAIT   = 300   # 5 minutes before giving up

if (-not $LegacyBearerAuth) {
    Write-Host "This legacy script no longer updates ~/.cursor/mcp.json by default." -ForegroundColor Yellow
    Write-Host "Use the Atlas MCP API-key config instead:"
    Write-Host "  url: https://atlas-mcp.healthcarecopilot.ai/mcp"
    Write-Host "  header: X-MCP-Api-Key"
    Write-Host ""
    Write-Host "To deliberately run the old bearer-token flow, pass -LegacyBearerAuth." -ForegroundColor Yellow
    exit 1
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Step([string]$msg) {
    Write-Host "`n>> $msg" -ForegroundColor Cyan
}

# Safe property read -- works on PowerShell 5 and 7
function Get-Prop($obj, [string]$name) {
    if ($null -eq $obj) { return $null }
    $p = $obj.PSObject.Properties[$name]
    if ($null -eq $p) { return $null }
    return $p.Value
}

function Invoke-Atlas([string]$path, [string]$json = '{}') {
    $raw = curl.exe -s -X POST "$BASE_URL$path" `
                    -H "Content-Type: application/json" `
                    -d $json
    if (-not $raw) { return $null }
    return $raw | ConvertFrom-Json
}

function Patch-McpJson([string]$accessToken) {
    $cfg = Get-Content $MCP_CONFIG -Raw | ConvertFrom-Json
    $cfg.mcpServers.'atlas-design-controls'.headers.Authorization = "Bearer $accessToken"
    $cfg | ConvertTo-Json -Depth 10 | Set-Content $MCP_CONFIG -Encoding UTF8
    Write-Host "   mcp.json updated." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Refresh path -- use a saved refresh token to get a new access token
# ---------------------------------------------------------------------------

if ($Refresh) {
    Write-Step "Refreshing access token..."

    if (-not (Test-Path $TOKEN_FILE)) {
        Write-Host "   No refresh token found at $TOKEN_FILE." -ForegroundColor Red
        Write-Host "   Run the script without -Refresh to do a full login first."
        exit 1
    }

    $refreshToken = (Get-Content $TOKEN_FILE -Raw).Trim()
    $response     = Invoke-Atlas "/auth/token/refresh" "{`"refresh_token`":`"$refreshToken`"}"

    $accessToken = Get-Prop $response 'access_token'
    if (-not $accessToken) {
        Write-Host "   Refresh failed -- response was:" -ForegroundColor Red
        $response | ConvertTo-Json | Write-Host
        exit 1
    }

    $newRefresh = Get-Prop $response 'refresh_token'
    if ($newRefresh) {
        $newRefresh | Set-Content $TOKEN_FILE -Encoding UTF8
    }

    Patch-McpJson $accessToken
    Write-Host "`nDone. Reload Cursor (Ctrl+Shift+P -> Reload Window) to pick up the new token." -ForegroundColor Green
    exit 0
}

# ---------------------------------------------------------------------------
# Full device-code login flow
# ---------------------------------------------------------------------------

Write-Step "Starting device-code flow..."

$raw          = curl.exe -s -X POST "$BASE_URL/auth/device/code"
$codeResponse = $raw | ConvertFrom-Json

$deviceCode = $codeResponse.device_code
$userCode   = $codeResponse.user_code
$verifyUrl  = if ($codeResponse.verification_uri) { $codeResponse.verification_uri } `
              else { "https://login.microsoft.com/device" }

if (-not $deviceCode -or -not $userCode) {
    Write-Host "   Failed to start device flow. Response was:" -ForegroundColor Red
    $raw | Write-Host
    exit 1
}

Write-Host ""
Write-Host "  +------------------------------------------+" -ForegroundColor Yellow
Write-Host "  |  Your code:  " -ForegroundColor Yellow -NoNewline
Write-Host $userCode -ForegroundColor White -NoNewline
Write-Host "                   |" -ForegroundColor Yellow
Write-Host "  +------------------------------------------+" -ForegroundColor Yellow
Write-Host ""
Write-Host "  1. A browser tab will open now."
Write-Host "  2. Enter the code above and sign in with your Entra account."
Write-Host "  3. If this is your first time, also visit $BASE_URL once (JIT provisioning)."
Write-Host ""

Start-Process $verifyUrl

# ---------------------------------------------------------------------------
# Poll for the token
# ---------------------------------------------------------------------------

Write-Step "Waiting for you to complete sign-in (timeout: $MAX_WAIT s)..."

$elapsed      = 0
$accessToken  = $null
$refreshToken = $null

while ($elapsed -lt $MAX_WAIT) {
    Start-Sleep -Seconds $POLL_SECS
    $elapsed += $POLL_SECS

    $response    = Invoke-Atlas "/auth/device/token" "{`"device_code`":`"$deviceCode`"}"
    $accessToken = Get-Prop $response 'access_token'

    if ($accessToken) {
        $refreshToken = Get-Prop $response 'refresh_token'
        break
    }

    $errVal = Get-Prop $response 'error'
    if ($errVal -and $errVal -notmatch 'authorization_pending|slow_down') {
        Write-Host "   [$elapsed s] unexpected error: $errVal -- backing off 30s" -ForegroundColor Yellow
        Start-Sleep -Seconds 30
        $elapsed += 30
    } else {
        $pending = if ($errVal) { $errVal } else { "polling..." }
        Write-Host "   [$elapsed s] $pending" -ForegroundColor DarkGray
    }
}

if (-not $accessToken) {
    Write-Host "`nTimed out waiting for sign-in. Run the script again when ready." -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
# Persist tokens
# ---------------------------------------------------------------------------

Write-Step "Token received. Updating mcp.json..."
Patch-McpJson $accessToken

if ($refreshToken) {
    $refreshToken | Set-Content $TOKEN_FILE -Encoding UTF8
    Write-Host "   Refresh token saved to $TOKEN_FILE" -ForegroundColor Green
    Write-Host "   To refresh later: .\scripts\setup_atlas_mcp_token.ps1 -Refresh"
}

Write-Host ""
Write-Host "All done! Reload Cursor (Ctrl+Shift+P -> Reload Window) to activate the Atlas MCP." -ForegroundColor Green
