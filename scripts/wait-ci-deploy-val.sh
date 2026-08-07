#!/usr/bin/env bash
# Wait for CI run to succeed, then promote to validation (leo-ai-val).
set -euo pipefail

CI_RUN_ID="${1:-31126039780}"
IMAGE_TAG="${2:-sha-e1ef04c6cab855a850015eed0197d24633a4d464}"
POLL_SECONDS="${3:-60}"
MAX_WAIT_SECONDS="${4:-7200}"

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

echo "Waiting for CI run ${CI_RUN_ID} (max ${MAX_WAIT_SECONDS}s, poll ${POLL_SECONDS}s)"
echo "Val image tag: ${IMAGE_TAG}"

elapsed=0
while [ "$elapsed" -lt "$MAX_WAIT_SECONDS" ]; do
  json="$(gh run view "$CI_RUN_ID" --json status,conclusion,url 2>/dev/null || true)"
  status="$(echo "$json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo unknown)"
  conclusion="$(echo "$json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('conclusion') or '')" 2>/dev/null || echo "")"
  url="$(echo "$json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('url',''))" 2>/dev/null || echo "")"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) CI status=${status} conclusion=${conclusion} ${url}"

  if [ "$status" = "completed" ]; then
    if [ "$conclusion" = "success" ]; then
      echo "CI succeeded. Triggering CD - Deploy to validation..."
      gh workflow run cd-deploy.yml \
        --ref main \
        -f environment=val \
        -f image_tag="$IMAGE_TAG"
      sleep 10
      deploy_run="$(gh run list --workflow "CD - Deploy" --limit 1 --json databaseId --jq '.[0].databaseId')"
      echo "CD run: https://github.com/Healthcare-Copilot/LEO-AI-CORE/actions/runs/${deploy_run}"
      gh run watch "$deploy_run" --exit-status
      echo "Validation deploy finished."
      exit 0
    fi
    echo "CI finished with conclusion=${conclusion}; not deploying."
    exit 1
  fi
  sleep "$POLL_SECONDS"
  elapsed=$((elapsed + POLL_SECONDS))
done

echo "Timed out waiting for CI run ${CI_RUN_ID}"
exit 1
