#!/usr/bin/env bash
# Pull Key Vault secrets into secrets/.env.secrets for offline local dev.
# macOS/Linux equivalent of sync-secrets-local.ps1 (no PowerShell required).
#
# Usage:
#   ./scripts/sync-secrets-local.sh dev
#   ./scripts/sync-secrets-local.sh val
#   VAULT_NAME=leoai-dev-kv ./scripts/sync-secrets-local.sh dev
#
# Subscriptions:
#   dev  -> Main SaaS Subscription, vault leoai-dev-kv
#   val  -> Multi Tenanted - LEO Test, vault mizaicai-val-kv
#   prod -> Multi Tenanted - LEO Production, vault mizaicai-prod-kv
#
# Requirements: az CLI logged in, Key Vault Secrets User on the vault.
set -euo pipefail

ENVIRONMENT="${1:-}"
OUT_FILE="${2:-secrets/.env.secrets}"

if [[ -z "$ENVIRONMENT" ]]; then
  echo "Usage: $0 <dev|val|prod> [out-file]" >&2
  exit 1
fi

case "$ENVIRONMENT" in
  dev|val|prod) ;;
  *)
    echo "Environment must be dev, val, or prod (got: $ENVIRONMENT)" >&2
    exit 1
    ;;
esac

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Default vault + subscription per environment (Main SaaS for local/dev).
case "$ENVIRONMENT" in
  dev)
    DEFAULT_VAULT="leoai-dev-kv"
    DEFAULT_SUB="Main SaaS Subscription"
    ;;
  val)
    DEFAULT_VAULT="mizaicai-val-kv"
    DEFAULT_SUB="Multi Tenanted - LEO Test"
    ;;
  prod)
    DEFAULT_VAULT="mizaicai-prod-kv"
    DEFAULT_SUB="Multi Tenanted - LEO Production"
    ;;
esac

KV_NAME="${VAULT_NAME:-$DEFAULT_VAULT}"
SUB_NAME="${AZURE_SUBSCRIPTION:-$DEFAULT_SUB}"

echo "  Subscription: $SUB_NAME"
echo "  Vault:        $KV_NAME"
az account set --subscription "$SUB_NAME" >/dev/null

python3 - "$ENVIRONMENT" "$OUT_FILE" "$KV_NAME" <<'PY'
import subprocess
import sys
from pathlib import Path

from libs.keyvault.loader import SECRET_MAP

environment = sys.argv[1]
out_file = Path(sys.argv[2])
kv_name = sys.argv[3]

EXTRA_MAP = {
    "azure-storage-connection-string": "AZURE_STORAGE_CONNECTION_STRING",
}

kv_to_env = {kv: env for env, kv in SECRET_MAP.items()}
for kv, env in EXTRA_MAP.items():
    kv_to_env[kv] = env

lines = [
    f"# !! DO NOT COMMIT -- generated from {kv_name} !!",
    f"# Refresh: ./scripts/sync-secrets-local.sh {environment}",
    "",
    "NEO4J_USER=neo4j",
    "KNOWLEDGE_GRAPH_NEO4J_USERNAME=neo4j",
    "GUIDELINE_NEO4J_USER=neo4j",
]

ok = err = 0
for kv_name_key in sorted(kv_to_env, key=lambda k: kv_to_env[k]):
    env_var = kv_to_env[kv_name_key]
    proc = subprocess.run(
        [
            "az", "keyvault", "secret", "show",
            "--vault-name", kv_name,
            "--name", kv_name_key,
            "--query", "value",
            "-o", "tsv",
        ],
        capture_output=True,
        text=True,
    )
    val = proc.stdout.strip()
    if proc.returncode == 0 and val:
        lines.append(f"{env_var}={val}")
        print(f"  OK    {kv_name_key} -> {env_var}")
        ok += 1
    else:
        lines.append(f"# {env_var}=  # not found in {kv_name}")
        print(f"  SKIP  {kv_name_key}", file=sys.stderr)
        err += 1

out_file.parent.mkdir(parents=True, exist_ok=True)
out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"\nWritten {ok} secrets to {out_file} ({err} skipped).")
print("Leave AZURE_KEYVAULT_URL unset locally; services read secrets/.env.secrets.")
PY
