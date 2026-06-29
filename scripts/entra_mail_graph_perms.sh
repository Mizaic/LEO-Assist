#!/usr/bin/env bash
# -- LEO AI Core - Mail Graph app: application permissions -----------------
# Adds Microsoft Graph *application* permissions for the cross-tenant mail
# app (MAIL_GRAPH_*). Run in the Entra tenant that owns the @mizaic.com mailbox.
#
# Prerequisites:
#   az login              (as admin of the mizaic.com / corporate tenant)
#   az account set --subscription <any-sub-in-that-tenant-or-use-tenant-flags>
#
# Inputs:
#   MAIL_GRAPH_APP_ID   App (client) ID of the mail-only app registration.
#                         Override with --app-id <guid>.
#
# Grants (application roles):
#   Mail.Send, Mail.ReadWrite
#
# After running, create a client secret on the app and store in Key Vault:
#   mail-graph-tenant-id, mail-graph-client-id, mail-graph-client-secret
set -euo pipefail

GRAPH_SP_APPID="00000003-0000-0000-c000-000000000000"

MAIL_GRAPH_APP_ID="${MAIL_GRAPH_APP_ID:-}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --app-id) MAIL_GRAPH_APP_ID="$2"; shift 2 ;;
        *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "$MAIL_GRAPH_APP_ID" ]]; then
    echo "MAIL_GRAPH_APP_ID not set. Pass --app-id <guid> or export MAIL_GRAPH_APP_ID." >&2
    exit 2
fi

echo "=== Adding Microsoft Graph application permissions to mail Graph app ==="
echo "  app id: $MAIL_GRAPH_APP_ID"

resolve_app_role() {
    local ROLE_VALUE="$1"
    az ad sp show --id "$GRAPH_SP_APPID" \
        --query "appRoles[?value=='${ROLE_VALUE}' && contains(allowedMemberTypes, 'Application')].id | [0]" -o tsv
}

MAIL_SEND=$(resolve_app_role Mail.Send)
MAIL_READWRITE=$(resolve_app_role Mail.ReadWrite)

for v in "$MAIL_SEND" "$MAIL_READWRITE"; do
    if [[ -z "$v" || "$v" == "None" ]]; then
        echo "Failed to resolve a Graph application role id; aborting." >&2
        exit 3
    fi
done

REQUIRED_RESOURCE_ACCESS=$(cat <<EOF
[
  {
    "resourceAppId": "${GRAPH_SP_APPID}",
    "resourceAccess": [
      { "id": "${MAIL_SEND}", "type": "Role" },
      { "id": "${MAIL_READWRITE}", "type": "Role" }
    ]
  }
]
EOF
)

echo ""
echo "Patching mail app registration with Mail.Send + Mail.ReadWrite..."
az ad app update \
    --id "$MAIL_GRAPH_APP_ID" \
    --required-resource-accesses "$REQUIRED_RESOURCE_ACCESS" \
    --output none

az ad sp create --id "$MAIL_GRAPH_APP_ID" --output none 2>/dev/null || true

TENANT_ID=$(az account show --query tenantId -o tsv)
echo ""
echo "=== Admin consent (corporate tenant) ======================================"
echo "Grant admin consent in Entra portal, or visit:"
echo ""
echo "  https://login.microsoftonline.com/${TENANT_ID}/adminconsent?client_id=${MAIL_GRAPH_APP_ID}"
echo ""
echo "Then create a client secret and push to Key Vault via migrate-secrets.ps1:"
echo "  MAIL_GRAPH_TENANT_ID=${TENANT_ID}"
echo "  MAIL_GRAPH_CLIENT_ID=${MAIL_GRAPH_APP_ID}"
echo "  MAIL_GRAPH_CLIENT_SECRET=<new-secret>"
