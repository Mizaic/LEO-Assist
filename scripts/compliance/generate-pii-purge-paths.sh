#!/usr/bin/env bash
# Append explicit paths from the security cleanup commit to the delete list.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${REPO_ROOT}/scripts/compliance/pii-purge-paths-delete.generated.txt"
BASE="${REPO_ROOT}/scripts/compliance/pii-purge-paths-delete.txt"

SECURITY_COMMIT="$(git -C "$REPO_ROOT" rev-list -n 1 --grep 'remove PHI cohort data' HEAD 2>/dev/null || true)"

{
  echo "# Auto-generated $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# Merged with ${BASE}"
  echo
  cat "$BASE"
  echo
  if [[ -n "$SECURITY_COMMIT" ]]; then
    echo "# --- From security commit ${SECURITY_COMMIT:0:8} ---"
    git -C "$REPO_ROOT" show "$SECURITY_COMMIT" --name-only --format= \
      | tail -n +2 \
      | grep -v '^\.gitignore$' \
      || true
  fi
  echo
  echo "# --- gitignore-tracked (should be empty on clean tree) ---"
  git -C "$REPO_ROOT" ls-files -ci --exclude-standard || true
} | awk '!seen[$0]++' >"$OUT"

echo "Wrote $OUT ($(wc -l <"$OUT" | tr -d ' ') lines)"
