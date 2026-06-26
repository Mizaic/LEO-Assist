# -- LEO AI Core - Entra ID App Registration Setup -------------------------
# Run once as Entra admin after Bicep deployment creates the managed identities.
#
# Prerequisites:
#   az login            (as Entra admin)
#   az account set --subscription <your-subscription-id>
#
# What this script does:
#   1. Registers 4 service apps with a "Call" app role each
#   2. Retrieves the managed identity principal ID from leo-ai-{env}
#   3. Grants app role assignments so the managed identity can call all services
#   4. Writes the app IDs into Key Vault for reference
#
param(
    [string]$Environment = "dev"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ResourceGroup = "leo-ai-$Environment"
$KvName = "mizaicai-$Environment-kv"

Write-Host "=== Registering Entra service apps for environment: $Environment ==="

# -- Helper: create or retrieve an app registration with a Call app role ---
function Register-ServiceApp {
    param([string]$AppName)

    $existing = az ad app list --display-name $AppName --query "[0].appId" -o tsv 2>$null
    if ($existing -and $existing -ne "None") {
        Write-Host "  App '$AppName' already exists: $existing"
        return $existing
    }

    $roleId = [Guid]::NewGuid().ToString()
    # Write JSON to a temp file -- avoids all PowerShell/az CLI quoting issues
    $tmpFile = [System.IO.Path]::GetTempFileName()
    [System.IO.File]::WriteAllText($tmpFile, "[{`"allowedMemberTypes`":[`"Application`"],`"description`":`"Allows caller services to invoke this API`",`"displayName`":`"Call`",`"id`":`"$roleId`",`"isEnabled`":true,`"value`":`"Call`"}]")

    $appId = az ad app create `
        --display-name $AppName `
        --sign-in-audience AzureADMyOrg `
        --app-roles "@$tmpFile" `
        --query appId -o tsv
    Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -ne 0) { throw "Failed to create app $AppName" }

    az ad sp create --id $appId --output none
    if ($LASTEXITCODE -ne 0) { throw "Failed to create service principal for $AppName" }

    Write-Host "  Created '$AppName': $appId"
    return $appId
}

# -- Register 4 internal service apps -------------------------------------
Write-Host ""
Write-Host "Registering service apps ..."

$TermAppId      = Register-ServiceApp "leo-terminology-api"
$ModelAppId     = Register-ServiceApp "leo-model-inference"
$FhirAppId      = Register-ServiceApp "leo-fhir-api"
$AnalyticsAppId = Register-ServiceApp "leo-analytics-api"

# -- Retrieve managed identity principal ID --------------------------------
Write-Host ""
Write-Host "Retrieving managed identity from $ResourceGroup ..."

$IdentityName = "mizaicai-$Environment-id"
$IdentityPrincipalId = az identity show `
    --name $IdentityName `
    --resource-group $ResourceGroup `
    --query principalId -o tsv
if ($LASTEXITCODE -ne 0) { throw "Could not retrieve managed identity $IdentityName" }

Write-Host "  $IdentityName => $IdentityPrincipalId"

# -- Helper: grant the Call app role on a target app ----------------------
function Grant-CallRole {
    param([string]$AssigneePrincipalId, [string]$TargetAppId, [string]$TargetAppName)

    $SpObjectId = az ad sp show --id $TargetAppId --query id -o tsv
    $RoleId     = az ad sp show --id $TargetAppId `
                      --query "appRoles[?value=='Call'].id | [0]" -o tsv

    $existingJson = az rest `
        --method GET `
        --url "https://graph.microsoft.com/v1.0/servicePrincipals/$SpObjectId/appRoleAssignedTo" `
        --query "value[?principalId=='$AssigneePrincipalId' && appRoleId=='$RoleId'].id | [0]" `
        -o tsv 2>$null

    if ($existingJson -and $existingJson -ne "None") {
        Write-Host "  Already granted Call on $TargetAppName"
        return
    }

    $tmpBody = [System.IO.Path]::GetTempFileName()
    [System.IO.File]::WriteAllText($tmpBody, "{`"principalId`":`"$AssigneePrincipalId`",`"resourceId`":`"$SpObjectId`",`"appRoleId`":`"$RoleId`"}")

    az rest `
        --method POST `
        --url "https://graph.microsoft.com/v1.0/servicePrincipals/$SpObjectId/appRoleAssignedTo" `
        --body "@$tmpBody" `
        --output none
    Remove-Item $tmpBody -Force -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -ne 0) { throw "Failed to grant Call on $TargetAppName" }
    Write-Host "  Granted Call on $TargetAppName to $AssigneePrincipalId"
}

# -- Grant app role assignments --------------------------------------------
Write-Host ""
Write-Host "Granting app role assignments ..."

Grant-CallRole $IdentityPrincipalId $TermAppId      "leo-terminology-api"
Grant-CallRole $IdentityPrincipalId $ModelAppId     "leo-model-inference"
Grant-CallRole $IdentityPrincipalId $FhirAppId      "leo-fhir-api"
Grant-CallRole $IdentityPrincipalId $AnalyticsAppId "leo-analytics-api"

# -- Write app IDs to Key Vault -------------------------------------------
Write-Host ""
Write-Host "Writing app IDs to Key Vault $KvName ..."

az keyvault secret set --vault-name $KvName --name "terminology-api-app-id" --value $TermAppId      --output none
az keyvault secret set --vault-name $KvName --name "model-inference-app-id"  --value $ModelAppId     --output none
az keyvault secret set --vault-name $KvName --name "fhir-api-app-id"         --value $FhirAppId      --output none
az keyvault secret set --vault-name $KvName --name "analytics-api-app-id"    --value $AnalyticsAppId --output none

Write-Host ""
Write-Host "=== Done. App IDs ==="
Write-Host "  TERMINOLOGY_API_APP_ID  = $TermAppId"
Write-Host "  MODEL_INFERENCE_APP_ID  = $ModelAppId"
Write-Host "  FHIR_API_APP_ID         = $FhirAppId"
Write-Host "  ANALYTICS_API_APP_ID    = $AnalyticsAppId"
Write-Host ""
Write-Host "Add these to infra/bicep/parameters/$Environment.bicepparam as plain config params."
