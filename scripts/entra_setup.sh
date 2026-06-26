#!/usr/bin/env bash
# -- LEO AI Core - Entra ID App Registration Setup -------------------------
# Run once as Entra admin after Bicep deployment creates the managed identities.
#
# Prerequisites:
#   az login            (as Entra admin)
#   az account set --subscription <your-subscription-id>
#
# What this script does:
#   1. Registers 4 service apps with a "Call" app role each
#   2. Retrieves the managed identity principal IDs from leo-ai-dev
#   3. Grants app role assignments: core-api and coding-worker can Call all services
#   4. Writes the app IDs as non-secret env vars into the Key Vault for reference
#
set -euo pipefail

ENVIRONMENT="${ENVIRONMENT:-dev}"
RESOURCE_GROUP="leo-ai-${ENVIRONMENT}"
KV_NAME="mizaicai-${ENVIRONMENT}-kv"

echo "=== Registering Entra service apps for environment: ${ENVIRONMENT} ==="

# -- Helper: create or retrieve an app registration with a Call app role ---
register_app() {
    local APP_NAME="$1"
    local EXISTING
    EXISTING=$(az ad app list --display-name "$APP_NAME" --query "[0].appId" -o tsv 2>/dev/null || true)

    if [[ -n "$EXISTING" && "$EXISTING" != "None" ]]; then
        echo "  App '$APP_NAME' already exists: $EXISTING"
        echo "$EXISTING"
        return
    fi

    local APP_ROLE_ID
    APP_ROLE_ID=$(python3 -c "import uuid; print(uuid.uuid4())")

    local APP_ID
    APP_ID=$(az ad app create \
        --display-name "$APP_NAME" \
        --sign-in-audience AzureADMyOrg \
        --app-roles "[{
            \"allowedMemberTypes\": [\"Application\"],
            \"description\": \"Allows caller services to invoke this API\",
            \"displayName\": \"Call\",
            \"id\": \"${APP_ROLE_ID}\",
            \"isEnabled\": true,
            \"value\": \"Call\"
        }]" \
        --query appId -o tsv)

    # Create a service principal so managed identities can be assigned roles
    az ad sp create --id "$APP_ID" --output none

    echo "  Created '$APP_NAME': $APP_ID"
    echo "$APP_ID"
}

# -- Register 4 internal service apps -------------------------------------
echo ""
echo "Registering service app: leo-terminology-api"
TERM_APP_ID=$(register_app "leo-terminology-api")

echo "Registering service app: leo-model-inference"
MODEL_APP_ID=$(register_app "leo-model-inference")

echo "Registering service app: leo-fhir-api"
FHIR_APP_ID=$(register_app "leo-fhir-api")

echo "Registering service app: leo-analytics-api"
ANALYTICS_APP_ID=$(register_app "leo-analytics-api")

# -- Retrieve managed identity principal IDs from ACA ----------------------
echo ""
echo "Retrieving managed identity principal IDs from ${RESOURCE_GROUP} ..."

IDENTITY_NAME="mizaicai-${ENVIRONMENT}-id"
IDENTITY_PRINCIPAL_ID=$(az identity show \
    --name "$IDENTITY_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query principalId -o tsv)

echo "  Managed identity: ${IDENTITY_NAME} => ${IDENTITY_PRINCIPAL_ID}"

# -- Grant app role assignments -------------------------------------------
# Helper: assign a "Call" app role on TARGET_APP to ASSIGNEE_PRINCIPAL
grant_call_role() {
    local ASSIGNEE_PRINCIPAL="$1"
    local TARGET_APP_ID="$2"
    local TARGET_APP_NAME="$3"

    local SP_OBJECT_ID
    SP_OBJECT_ID=$(az ad sp show --id "$TARGET_APP_ID" --query id -o tsv)

    local ROLE_ID
    ROLE_ID=$(az ad sp show --id "$TARGET_APP_ID" \
        --query "appRoles[?value=='Call'].id | [0]" -o tsv)

    local EXISTING
    EXISTING=$(az rest \
        --method GET \
        --url "https://graph.microsoft.com/v1.0/servicePrincipals/${SP_OBJECT_ID}/appRoleAssignedTo" \
        --query "value[?principalId=='${ASSIGNEE_PRINCIPAL}' && appRoleId=='${ROLE_ID}'].id | [0]" \
        -o tsv 2>/dev/null || true)

    if [[ -n "$EXISTING" && "$EXISTING" != "None" ]]; then
        echo "  Already granted Call on ${TARGET_APP_NAME}"
        return
    fi

    az rest \
        --method POST \
        --url "https://graph.microsoft.com/v1.0/servicePrincipals/${SP_OBJECT_ID}/appRoleAssignedTo" \
        --body "{
            \"principalId\": \"${ASSIGNEE_PRINCIPAL}\",
            \"resourceId\": \"${SP_OBJECT_ID}\",
            \"appRoleId\": \"${ROLE_ID}\"
        }" \
        --output none

    echo "  Granted Call on ${TARGET_APP_NAME} to principal ${ASSIGNEE_PRINCIPAL}"
}

echo ""
echo "Granting app role assignments ..."

# The single user-assigned managed identity covers all apps in this env
grant_call_role "$IDENTITY_PRINCIPAL_ID" "$TERM_APP_ID" "leo-terminology-api"
grant_call_role "$IDENTITY_PRINCIPAL_ID" "$MODEL_APP_ID" "leo-model-inference"
grant_call_role "$IDENTITY_PRINCIPAL_ID" "$FHIR_APP_ID" "leo-fhir-api"
grant_call_role "$IDENTITY_PRINCIPAL_ID" "$ANALYTICS_APP_ID" "leo-analytics-api"

# -- Write app IDs to Key Vault so services can read them at startup -------
echo ""
echo "Writing app IDs to Key Vault ${KV_NAME} ..."

az keyvault secret set --vault-name "$KV_NAME" --name "terminology-api-app-id" --value "$TERM_APP_ID" --output none
az keyvault secret set --vault-name "$KV_NAME" --name "model-inference-app-id"  --value "$MODEL_APP_ID"  --output none
az keyvault secret set --vault-name "$KV_NAME" --name "fhir-api-app-id"         --value "$FHIR_APP_ID"   --output none
az keyvault secret set --vault-name "$KV_NAME" --name "analytics-api-app-id"    --value "$ANALYTICS_APP_ID" --output none

echo ""
echo "=== Done. App IDs ==="
echo "  TERMINOLOGY_API_APP_ID  = ${TERM_APP_ID}"
echo "  MODEL_INFERENCE_APP_ID  = ${MODEL_APP_ID}"
echo "  FHIR_API_APP_ID         = ${FHIR_APP_ID}"
echo "  ANALYTICS_API_APP_ID    = ${ANALYTICS_APP_ID}"
echo ""
echo "Add these to infra/bicep/parameters/${ENVIRONMENT}.bicepparam as plain config params."
