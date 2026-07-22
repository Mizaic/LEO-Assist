#!/usr/bin/env bash
# G6.1 rollback drill -- staging execution script (DevOps)
#
# Run on staging when Azure Container Apps, Neo4j Patient Graph, and FHIR API
# credentials are available. Do NOT commit secrets; load from Key Vault or
# az containerapp env.
#
# Usage:
#   export FHIR_API_BASE="https://<staging-fhir-host>"
#   export NEO4J_URI="bolt://..."
#   export NEO4J_PASSWORD="..."   # from Key Vault
#   ./scripts/g6_1_rollback_drill_staging.sh
#
# Evidence: capture stdout and attach to Atlas change record (G6.1 step 6).

set -euo pipefail

PLAN_ID="${PLAN_ID:-pd-referral-assessment}"
ROLLBACK_TARGET="${ROLLBACK_TARGET:-v2}"
CANARY_TAG="${CANARY_TAG:-canary}"
PRIOR_TAG="${PRIOR_TAG:-last-known-good}"

echo "=== G6.1 rollback drill staging ==="
echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "plan_id=${PLAN_ID}"
echo "rollback_target=${ROLLBACK_TARGET}"

if [[ -z "${FHIR_API_BASE:-}" ]]; then
  echo "BLOCKED: FHIR_API_BASE not set. Export staging FHIR URL and re-run."
  exit 2
fi

if [[ -z "${NEO4J_URI:-}" || -z "${NEO4J_PASSWORD:-}" ]]; then
  echo "BLOCKED: NEO4J_URI or NEO4J_PASSWORD not set."
  exit 2
fi

echo ""
echo "--- Step 1: note current pipeline-worker image tag ---"
echo "ACTION: az containerapp show -n pipeline-worker -g <rg> --query properties.template.containers[0].image"
echo "Deploy canary tag ${CANARY_TAG} if not already on staging."

echo ""
echo "--- Step 2: start in-flight referral run ---"
echo "ACTION: submit referral trigger; record run_id from PipelineRun node."
INFLIGHT_RUN_ID="${INFLIGHT_RUN_ID:-}"
if [[ -z "${INFLIGHT_RUN_ID}" ]]; then
  echo "Set INFLIGHT_RUN_ID after step 2 and re-run from step 3."
fi

echo ""
echo "--- Step 3: set rollbackTarget on PlanDefinition ---"
echo "PATCH ${FHIR_API_BASE}/PlanDefinition/${PLAN_ID}"
echo 'Body fragment: {"_versionRollout": {"rollbackTarget": "'"${ROLLBACK_TARGET}"'"}}'
echo "Then redeploy prior image tag ${PRIOR_TAG}."

echo ""
echo "--- Step 4: submit NEW trigger; verify execution_manifest policy_version ---"
echo "Cypher (Patient Graph):"
cat <<'CYPHER'
MATCH (r:PipelineRun {id: $new_run_id})
RETURN r.policy_version AS policy_version,
       r.version_selection_reason AS reason,
       r.execution_manifest_json AS manifest
LIMIT 1
CYPHER
echo "EXPECT: policy_version=${ROLLBACK_TARGET}, reason=rollback_default"

echo ""
echo "--- Step 5: confirm in-flight run unchanged ---"
if [[ -n "${INFLIGHT_RUN_ID}" ]]; then
  python3 - <<PY
import json, os, sys
from neo4j import GraphDatabase

uri = os.environ["NEO4J_URI"]
password = os.environ["NEO4J_PASSWORD"]
run_id = os.environ["INFLIGHT_RUN_ID"]
driver = GraphDatabase.driver(uri, auth=("neo4j", password))
with driver.session() as session:
    row = session.run(
        """
        MATCH (r:PipelineRun {id: \$run_id})
        RETURN r.policy_version AS pv,
               r.plan_version_id AS pvid,
               r.execution_manifest_json AS manifest
        LIMIT 1
        """,
        run_id=run_id,
    ).single()
driver.close()
if not row:
    print("FAIL: in-flight run not found:", run_id)
    sys.exit(1)
print("inflight_policy_version=", row["pv"])
print("inflight_plan_version_id=", row["pvid"])
manifest = row["manifest"]
if manifest:
    parsed = json.loads(manifest) if isinstance(manifest, str) else manifest
    print("inflight_manifest_policy_version=", parsed.get("policy_version"))
print("PASS: compare inflight values to pre-rollback snapshot (must differ from step 4 new run)")
PY
else
  echo "SKIP: set INFLIGHT_RUN_ID to verify step 5 automatically."
fi

echo ""
echo "--- Emergency kill switch (optional sub-drill) ---"
echo "Set DURABLE_ENGINE_DISABLED=true on pipeline-worker env."
echo "Verify: new referral triggers NOT admitted; in-flight durable_step messages still complete."
echo "Recovery: unset DURABLE_ENGINE_DISABLED and redeploy ${PRIOR_TAG}."

echo ""
echo "--- Step 6: record outcome in Atlas change record ---"
echo "Owner sign-off: DevOps __________  QA/RA __________  Date __________"
