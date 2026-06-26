#!/usr/bin/env bash
# -- LEO AI Core - User-login app registration (Track D.1) -----------------
# Creates or updates the multi-tenant Entra app used for clinician OAuth login.
# Idempotent: safe to re-run; merges redirect URIs and patches manifest flags.
#
# Atlas trace: DC-INST-001 Track D.1, DC-DEP-001 Section 2
#
# Prerequisites:
#   az login (Entra admin in the deployment tenant)
#
# Usage:
#   ENVIRONMENT=val ./scripts/entra_user_login_setup.sh
#   ./scripts/entra_user_login_setup.sh --environment val --write-kv
#   ./scripts/entra_user_login_setup.sh --app-id <guid> --frontend-url https://example.com
#
# Options:
#   --environment dev|val|prod   Read frontendUrl from infra/bicep/parameters/{env}.bicepparam
#   --frontend-url URL           Override UI base URL (no trailing slash)
#   --display-name NAME          Default: Mizaic LEO AI {Dev|Val|Prod}
#   --app-id GUID                Update existing registration instead of create
#   --include-localhost          Add http://localhost:3000/auth/callback (dev only)
#   --secret-name NAME           Client secret display name (default: {env}-api)
#   --write-kv                   Push azure-ad-* secrets to mizaicai-{env}-kv
#   --skip-secret                Do not create or rotate a client secret
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ENVIRONMENT="${ENVIRONMENT:-}"
FRONTEND_URL="${FRONTEND_URL:-}"
DISPLAY_NAME="${DISPLAY_NAME:-}"
APP_ID="${APP_ID:-}"
INCLUDE_LOCALHOST="false"
SECRET_NAME=""
WRITE_KV="false"
SKIP_SECRET="false"

usage() {
    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
}

default_display_name() {
    case "$1" in
        dev)  echo "Mizaic LEO AI Dev" ;;
        val)  echo "Mizaic LEO AI Val" ;;
        prod) echo "Mizaic LEO AI Prod" ;;
        *)    echo "Mizaic LEO AI $1" ;;
    esac
}

read_frontend_url_from_bicepparam() {
    local env_name="$1"
    local param_file="${REPO_ROOT}/infra/bicep/parameters/${env_name}.bicepparam"
    if [[ ! -f "$param_file" ]]; then
        echo "Bicepparam not found: $param_file" >&2
        exit 1
    fi
    local line
    line=$(grep -E "^param frontendUrl = " "$param_file" | head -1 || true)
    if [[ -z "$line" ]]; then
        echo "frontendUrl not found in $param_file" >&2
        exit 1
    fi
    echo "$line" | sed -E "s/^param frontendUrl = '(.*)'/\1/"
}

normalize_frontend_url() {
    local url="$1"
    url="${url%/}"
    if [[ -z "$url" ]]; then
        echo "frontendUrl is empty" >&2
        exit 1
    fi
    if [[ "$url" != http://* && "$url" != https://* ]]; then
        echo "frontendUrl must start with http:// or https:// (got: $url)" >&2
        exit 1
    fi
    echo "$url"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --environment)     ENVIRONMENT="$2"; shift 2 ;;
        --frontend-url)    FRONTEND_URL="$2"; shift 2 ;;
        --display-name)      DISPLAY_NAME="$2"; shift 2 ;;
        --app-id)            APP_ID="$2"; shift 2 ;;
        --include-localhost) INCLUDE_LOCALHOST="true"; shift ;;
        --secret-name)       SECRET_NAME="$2"; shift 2 ;;
        --write-kv)          WRITE_KV="true"; shift ;;
        --skip-secret)       SKIP_SECRET="true"; shift ;;
        -h|--help)           usage ;;
        *) echo "Unknown arg: $1" >&2; usage ;;
    esac
done

if [[ -z "$ENVIRONMENT" && -z "$FRONTEND_URL" && -z "$APP_ID" ]]; then
    echo "Set --environment or --frontend-url (or --app-id with --frontend-url)." >&2
    exit 2
fi

if [[ -n "$ENVIRONMENT" && "$ENVIRONMENT" != dev && "$ENVIRONMENT" != val && "$ENVIRONMENT" != prod ]]; then
    echo "--environment must be dev, val, or prod." >&2
    exit 2
fi

if [[ "$INCLUDE_LOCALHOST" == "true" && -n "$ENVIRONMENT" && "$ENVIRONMENT" != dev ]]; then
    echo "Refusing --include-localhost for environment '$ENVIRONMENT' (DC-DEP-001: localhost only on dev)." >&2
    exit 2
fi

if [[ -z "$FRONTEND_URL" ]]; then
    FRONTEND_URL="$(read_frontend_url_from_bicepparam "$ENVIRONMENT")"
fi
FRONTEND_URL="$(normalize_frontend_url "$FRONTEND_URL")"
REDIRECT_URI="${FRONTEND_URL}/auth/callback"

if [[ -z "$DISPLAY_NAME" ]]; then
    if [[ -n "$ENVIRONMENT" ]]; then
        DISPLAY_NAME="$(default_display_name "$ENVIRONMENT")"
    else
        DISPLAY_NAME="Mizaic LEO AI"
    fi
fi

if [[ -z "$SECRET_NAME" ]]; then
  if [[ -n "$ENVIRONMENT" ]]; then
    SECRET_NAME="${ENVIRONMENT}-api"
  else
    SECRET_NAME="leo-api"
  fi
fi

build_redirect_list() {
    REDIRECT_LIST=("$REDIRECT_URI")
    if [[ "$INCLUDE_LOCALHOST" == "true" ]]; then
        REDIRECT_LIST+=("http://localhost:3000/auth/callback")
    fi
}

merge_redirect_uris() {
    local existing_json="$1"
    shift
    python3 - "$existing_json" "$@" <<'PY'
import json
import sys

raw = sys.argv[1]
if not raw or raw.strip() in ("", "null"):
    existing = []
else:
    parsed = json.loads(raw)
    existing = parsed if isinstance(parsed, list) else []

wanted = [u for u in sys.argv[2:] if u]
merged = []
for uri in wanted + existing:
    if uri and uri not in merged:
        merged.append(uri)
print(json.dumps(merged))
PY
}

wait_for_app() {
    local app_id="$1"
    local attempt
    for attempt in 1 2 3 4 5; do
        if az ad app show --id "$app_id" --query appId -o tsv &>/dev/null; then
            return 0
        fi
        sleep 2
    done
    echo "App $app_id is not visible yet in Entra ID." >&2
    return 1
}

patch_app_settings_via_graph() {
    local object_id="$1"
    local client_id="$2"
    local redirects_json="$3"
    local uri_count
    uri_count=$(python3 -c "import json,sys; print(len(json.loads(sys.argv[1])))" "$redirects_json")
    if [[ "$uri_count" -eq 0 ]]; then
        echo "No redirect URIs to apply." >&2
        return 1
    fi
    local tmp
    tmp=$(mktemp)
    python3 - "$redirects_json" "$client_id" > "$tmp" <<'PY'
import json
import sys

uris = json.loads(sys.argv[1])
client_id = sys.argv[2]
body = {
    "web": {
        "redirectUris": uris,
        "implicitGrantSettings": {
            "enableAccessTokenIssuance": False,
            "enableIdTokenIssuance": False,
        },
    },
    "signInAudience": "AzureADMultipleOrgs",
    "groupMembershipClaims": "SecurityGroup",
    "api": {"requestedAccessTokenVersion": 2},
    "identifierUris": [f"api://{client_id}"],
}
print(json.dumps(body))
PY
    if ! az rest --method PATCH \
        --url "https://graph.microsoft.com/v1.0/applications/${object_id}" \
        --headers "Content-Type=application/json" \
        --body "@${tmp}" \
        --output none; then
        rm -f "$tmp"
        echo "Graph PATCH failed for application ${object_id}." >&2
        return 1
    fi
    rm -f "$tmp"
}

echo "=== LEO user-login app registration (Track D.1) ==="
echo "  display name:  $DISPLAY_NAME"
echo "  redirect URI:  $REDIRECT_URI"
if [[ "$INCLUDE_LOCALHOST" == "true" ]]; then
    echo "  also adding:   http://localhost:3000/auth/callback"
fi

if [[ -z "$APP_ID" ]]; then
    EXISTING=$(az ad app list --display-name "$DISPLAY_NAME" --query "[0].appId" -o tsv 2>/dev/null || true)
    if [[ -n "$EXISTING" && "$EXISTING" != "None" ]]; then
        APP_ID="$EXISTING"
        echo "  found existing app: $APP_ID"
    fi
fi

build_redirect_list

if [[ -z "$APP_ID" ]]; then
    echo ""
    echo "Creating app registration ..."
    APP_ID=$(az ad app create \
        --display-name "$DISPLAY_NAME" \
        --sign-in-audience AzureADMultipleOrgs \
        --enable-access-token-issuance false \
        --enable-id-token-issuance false \
        --web-redirect-uris "${REDIRECT_LIST[@]}" \
        --query appId -o tsv)
    if [[ -z "$APP_ID" || "$APP_ID" == "None" ]]; then
        echo "Failed to obtain app id from az ad app create." >&2
        exit 1
    fi
    echo "  created app id: $APP_ID"
else
    echo ""
    echo "Updating app registration $APP_ID ..."
fi

wait_for_app "$APP_ID"

az ad sp create --id "$APP_ID" --output none 2>/dev/null || true

EXISTING_REDIRECTS=$(az ad app show --id "$APP_ID" --query "web.redirectUris" -o json)
MERGED_REDIRECTS=$(merge_redirect_uris "$EXISTING_REDIRECTS" "${REDIRECT_LIST[@]}")
OBJECT_ID=$(az ad app show --id "$APP_ID" --query id -o tsv)
if [[ -z "$OBJECT_ID" || "$OBJECT_ID" == "None" ]]; then
    echo "Could not resolve Entra object id for app ${APP_ID}." >&2
    exit 1
fi

echo ""
echo "Applying redirect URIs and manifest settings (Graph API) ..."
patch_app_settings_via_graph "$OBJECT_ID" "$APP_ID" "$MERGED_REDIRECTS"

TENANT_ID=$(az account show --query tenantId -o tsv)
CLIENT_SECRET=""

if [[ "$SKIP_SECRET" != "true" ]]; then
    echo ""
    echo "Creating client secret (display name: ${SECRET_NAME}) ..."
    CLIENT_SECRET=$(az ad app credential reset \
        --id "$APP_ID" \
        --display-name "$SECRET_NAME" \
        --years 1 \
        --query password -o tsv)
    echo "  secret created (store immediately; not shown again)"
fi

if [[ "$WRITE_KV" == "true" ]]; then
    if [[ -z "$ENVIRONMENT" ]]; then
        echo "--write-kv requires --environment." >&2
        exit 2
    fi
    KV_NAME="mizaicai-${ENVIRONMENT}-kv"
    echo ""
    echo "Writing azure-ad-* secrets to Key Vault ${KV_NAME} ..."
    az keyvault secret set --vault-name "$KV_NAME" --name "azure-ad-client-id" --value "$APP_ID" --output none
    az keyvault secret set --vault-name "$KV_NAME" --name "azure-ad-tenant-id" --value "$TENANT_ID" --output none
    if [[ -n "$CLIENT_SECRET" ]]; then
        az keyvault secret set --vault-name "$KV_NAME" --name "azure-ad-client-secret" --value "$CLIENT_SECRET" --output none
    else
        echo "  skipped azure-ad-client-secret (--skip-secret)"
    fi
fi

echo ""
echo "=== Done ================================================================"
echo "  AZURE_AD_TENANT_ID=${TENANT_ID}"
echo "  AZURE_AD_CLIENT_ID=${APP_ID}"
if [[ -n "$CLIENT_SECRET" ]]; then
    echo "  AZURE_AD_CLIENT_SECRET=<created; copy from Key Vault or re-run without --skip-secret>"
fi
echo ""
echo "Add to secrets/.env (if not using --write-kv), then migrate-secrets.ps1:"
echo "  AZURE_AD_TENANT_ID=${TENANT_ID}"
echo "  AZURE_AD_CLIENT_ID=${APP_ID}"
if [[ -n "$CLIENT_SECRET" ]]; then
    echo "  AZURE_AD_CLIENT_SECRET=${CLIENT_SECRET}"
fi
echo ""
echo "Optional: admin portal Graph permissions (Track D.4):"
echo "  USER_LOGIN_APP_ID=${APP_ID} REDIRECT_URI=${REDIRECT_URI} ./scripts/entra_user_login_graph_perms.sh"
