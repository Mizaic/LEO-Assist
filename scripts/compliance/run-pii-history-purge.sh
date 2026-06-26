#!/usr/bin/env bash
# Purge PHI paths from git history on Mizaic/LEO-AI-CORE.
#
# Context: HEAD is clean (manual commit 134ff31a). This removes PHI that still
# exists in older commits (encounter_audit DBs, data/ cohort exports, etc.).
#
# Usage:
#   ./scripts/compliance/run-pii-history-purge.sh              # pre-flight only
#   ./scripts/compliance/run-pii-history-purge.sh --execute    # rewrite + push
#
# Options (env):
#   PII_PURGE_REMOTE   default https://github.com/Mizaic/LEO-AI-CORE.git
#   PII_PURGE_BRANCH   default main
#   PII_PURGE_WORK_DIR default /tmp/LEO-AI-CORE-pii-purge-$$
#   PII_PURGE_IN_PLACE set to 1 to rewrite the current checkout (not recommended)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DELETE_LIST="${REPO_ROOT}/scripts/compliance/pii-purge-paths-delete.txt"
REPLACE_LIST="${REPO_ROOT}/scripts/compliance/pii-purge-replacements.txt"
REMOTE_URL="${PII_PURGE_REMOTE:-https://github.com/Mizaic/LEO-AI-CORE.git}"
BRANCH="${PII_PURGE_BRANCH:-main}"
WORK_DIR="${PII_PURGE_WORK_DIR:-/tmp/LEO-AI-CORE-pii-purge-$$}"
EXECUTE=false
IN_PLACE="${PII_PURGE_IN_PLACE:-0}"

if [[ "${1:-}" == "--execute" ]]; then
  EXECUTE=true
fi

if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "Install git-filter-repo: brew install git-filter-repo" >&2
  exit 1
fi

preflight_history_scan() {
  local repo="$1"
  echo "History scan (git log -S):"
  local needles=(
    'GHAYATH'
    '4187508279'
    'HORNE, Jonathan'
    'encounter_audit.db'
  )
  for needle in "${needles[@]}"; do
    local count
    count="$(git -C "$repo" log --all -S "$needle" --oneline 2>/dev/null | wc -l | tr -d ' ')"
    printf "  %-22s %s commits\n" "$needle" "$count"
  done
  echo
}

split_delete_lists() {
  local src="$1"
  local paths="$2"
  local globs="$3"
  : >"$paths"
  : >"$globs"
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -z "$line" ]] && continue
    if [[ "$line" == glob:* ]]; then
      echo "${line#glob:}" >>"$globs"
    else
      echo "$line" >>"$paths"
    fi
  done <"$src"
  if git -C "$TARGET" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$TARGET" ls-files -ci --exclude-standard >>"$paths" 2>/dev/null || true
  fi
  sort -u "$paths" -o "$paths"
  sort -u "$globs" -o "$globs"
}

echo "== PII history purge (post manual cleanup) =="
echo "Remote:   $REMOTE_URL"
echo "Branch:   $BRANCH"
echo "Execute:  $EXECUTE"
echo "In place: $IN_PLACE"
echo

preflight_history_scan "$REPO_ROOT"

if [[ "$IN_PLACE" == "1" ]]; then
  TARGET="$REPO_ROOT"
else
  TARGET="$WORK_DIR"
  if [[ -d "$TARGET" ]]; then
    echo "Work dir exists: $TARGET" >&2
    exit 1
  fi
  echo "Cloning $REMOTE_URL (branch $BRANCH) -> $TARGET"
  git clone -b "$BRANCH" --single-branch "$REMOTE_URL" "$TARGET"
fi

"${REPO_ROOT}/scripts/compliance/generate-pii-purge-paths.sh" >/dev/null
PATHS_FILE="/tmp/pii-purge-paths-$$.txt"
GLOBS_FILE="/tmp/pii-purge-globs-$$.txt"
MERGED_LIST="${REPO_ROOT}/scripts/compliance/pii-purge-paths-delete.generated.txt"
split_delete_lists "$MERGED_LIST" "$PATHS_FILE" "$GLOBS_FILE"

PATH_COUNT="$(wc -l <"$PATHS_FILE" | tr -d ' ')"
GLOB_COUNT="$(wc -l <"$GLOBS_FILE" | tr -d ' ')"
echo "Delete paths: $PATH_COUNT"
echo "Delete globs: $GLOB_COUNT"
head -15 "$GLOBS_FILE" 2>/dev/null || true
echo

if [[ "$EXECUTE" != true ]]; then
  echo "Dry run complete."
  echo "  Review: scripts/compliance/pii-purge-paths-delete.generated.txt"
  echo "  Execute: PII_PURGE_WORK_DIR=$TARGET $0 --execute"
  echo
  echo "After purge, verify:"
  echo "  git log -S 'GHAYATH' --oneline    # expect 0"
  echo "  git log -S '4187508279' --oneline # expect 0"
  exit 0
fi

read -r -p "Rewrite history and force-push to $REMOTE_URL? [y/N] " ans
[[ "${ans:-N}" == "y" ]] || exit 1

cd "$TARGET"

FILTER_ARGS=(--invert-paths --force)
if [[ -s "$PATHS_FILE" ]]; then
  FILTER_ARGS+=(--paths-from-file "$PATHS_FILE")
fi
while IFS= read -r glob || [[ -n "$glob" ]]; do
  [[ -z "$glob" ]] && continue
  FILTER_ARGS+=(--path-glob "$glob")
done <"$GLOBS_FILE"

echo "Step 1/3: delete PHI paths from history ..."
git filter-repo "${FILTER_ARGS[@]}"

echo "Step 2/3: replace lingering identifiers ..."
git filter-repo --replace-text "$REPLACE_LIST" --force

echo "Step 3/3: force-push ..."
git remote add origin "$REMOTE_URL" 2>/dev/null || git remote set-url origin "$REMOTE_URL"
git push --force origin "$BRANCH"

echo
preflight_history_scan "$TARGET"
echo "Done. Temp clone: $TARGET (rm -rf when verified)"
