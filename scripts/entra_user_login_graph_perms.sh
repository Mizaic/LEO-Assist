#!/usr/bin/env bash
# -- LEO AI Core - User-login app: Graph delegated permissions ------------
# Adds the Microsoft Graph delegated scopes the /admin/portal Entra
# extension uses (DI-31F4C232, DI-6CF7FCE0). Idempotent.
#
# Prerequisites:
#   az login              (as the LEO Entra admin)
#   az account set --subscription <your-subscription-id>
#
# Inputs:
#   USER_LOGIN_APP_ID     The appId (GUID) of the existing user-login
#                         multi-tenant app reg (the one whose appId is
#                         stored in Key Vault as `azure-ad-client-id`).
#                         You can override with --app-id <guid>.
#
# What this script does:
#   1. Adds five Microsoft Graph delegated scopes to the app's
#      requiredResourceAccess block (Domain.Read.All, User.Read.All,
#      Group.Read.All, Group.ReadWrite.All, GroupMember.ReadWrite.All).
#   2. Prints the per-tenant admin-consent URL each customer's Entra
#      admin must visit to grant these scopes for their tenant.
#
# This script does NOT grant consent on behalf of customer tenants.
# Customer tenants must consent themselves via the printed URL.
set -euo pipefail

GRAPH_SP_APPID="00000003-0000-0000-c000-000000000000"

USER_LOGIN_APP_ID="${USER_LOGIN_APP_ID:-}"
REDIRECT_URI="${REDIRECT_URI:-https://leoai.example.com/api/auth/callback}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --app-id)         USER_LOGIN_APP_ID="$2"; shift 2 ;;
        --redirect-uri)   REDIRECT_URI="$2"; shift 2 ;;
        *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "$USER_LOGIN_APP_ID" ]]; then
    echo "USER_LOGIN_APP_ID not set. Pass --app-id <guid> or export USER_LOGIN_APP_ID." >&2
    exit 2
fi

echo "=== Adding Microsoft Graph delegated permissions to user-login app ==="
echo "  app id: $USER_LOGIN_APP_ID"

# Resolve scope GUIDs from Microsoft Graph's service principal in this
# tenant. Scope ids are constants across tenants, but resolving them
# defensively means a Graph schema rename is caught immediately.
GRAPH_SP_OBJECT_ID=$(az ad sp show --id "$GRAPH_SP_APPID" --query id -o tsv)

resolve_scope() {
    local SCOPE_NAME="$1"
    az ad sp show --id "$GRAPH_SP_APPID" \
        --query "oauth2PermissionScopes[?value=='${SCOPE_NAME}'].id | [0]" -o tsv
}

DOMAIN_READ_ALL=$(resolve_scope Domain.Read.All)
USER_READ_ALL=$(resolve_scope User.Read.All)
GROUP_READ_ALL=$(resolve_scope Group.Read.All)
GROUP_READWRITE_ALL=$(resolve_scope Group.ReadWrite.All)
GROUPMEMBER_READWRITE_ALL=$(resolve_scope GroupMember.ReadWrite.All)

for v in "$DOMAIN_READ_ALL" "$USER_READ_ALL" "$GROUP_READ_ALL" \
         "$GROUP_READWRITE_ALL" "$GROUPMEMBER_READWRITE_ALL"; do
    if [[ -z "$v" || "$v" == "None" ]]; then
        echo "Failed to resolve a Graph scope id; aborting." >&2
        exit 3
    fi
done

REQUIRED_RESOURCE_ACCESS=$(cat <<EOF
[
  {
    "resourceAppId": "${GRAPH_SP_APPID}",
    "resourceAccess": [
      { "id": "${DOMAIN_READ_ALL}",            "type": "Scope" },
      { "id": "${USER_READ_ALL}",              "type": "Scope" },
      { "id": "${GROUP_READ_ALL}",             "type": "Scope" },
      { "id": "${GROUP_READWRITE_ALL}",        "type": "Scope" },
      { "id": "${GROUPMEMBER_READWRITE_ALL}",  "type": "Scope" }
    ]
  }
]
EOF
)

echo ""
echo "Patching app registration with required Graph delegated scopes..."
az ad app update \
    --id "$USER_LOGIN_APP_ID" \
    --required-resource-accesses "$REQUIRED_RESOURCE_ACCESS" \
    --output none

echo "  Done."

# -- Print the per-tenant admin-consent URL --------------------------------
SCOPES="https://graph.microsoft.com/Domain.Read.All https://graph.microsoft.com/User.Read.All https://graph.microsoft.com/Group.Read.All https://graph.microsoft.com/Group.ReadWrite.All https://graph.microsoft.com/GroupMember.ReadWrite.All"
SCOPES_ENC=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$SCOPES")
REDIRECT_ENC=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$REDIRECT_URI")

echo ""
echo "=== Per-tenant admin consent URL =========================================="
echo "Each customer's Entra admin must visit this URL (substituting their tenant"
echo "id for {tenant_id}) to grant LEO the delegated Graph permissions:"
echo ""
echo "  https://login.microsoftonline.com/{tenant_id}/v2.0/adminconsent?client_id=${USER_LOGIN_APP_ID}&redirect_uri=${REDIRECT_ENC}&scope=${SCOPES_ENC}"
echo ""
echo "If a customer chooses not to grant consent, the /admin/portal will fall"
echo "back to the manual / Neo4j-only mode (DI-5A18A227)."
