#!/usr/bin/env bash
# LEO-AI-CORE - Local Development Startup (macOS / Linux)
# Creates / activates .venv, installs deps, starts microservices in new Terminal windows.
#
# Usage:
#   ./scripts/start_leo-ai-core.sh
#   ./scripts/start_leo-ai-core.sh --skip-install
#   ./scripts/start_leo-ai-core.sh --no-workers
#   ./scripts/start_leo-ai-core.sh --no-model-inference
#   ./scripts/start_leo-ai-core.sh --no-training-worker
#   ./scripts/start_leo-ai-core.sh --no-research-worker
#   ./scripts/start_leo-ai-core.sh --mcp
#   ./scripts/start_leo-ai-core.sh --no-mcp
#   ./scripts/start_leo-ai-core.sh --services api,ui
#   ./scripts/start_leo-ai-core.sh --pipeline-workers 3
#   ./scripts/start_leo-ai-core.sh --term-workers 3
#   ./scripts/start_leo-ai-core.sh --e2e
#
# Environment overrides (optional):
#   LEO_PYTHON  -- full path to python3.12 used to create .venv (must be 3.12.x; matches CI)
#   API_PORT, TERM_PORT, FHIR_PORT, ANALYTICS_PORT, MODEL_INFERENCE_PORT,
#   TRAINING_WORKER_PORT, PIPELINE_WORKER_PORT, RESEARCH_WORKER_PORT, UI_PORT,
#   PIPELINE_WORKERS, TERM_WORKERS, TRAINING_JOB_TIMEOUT_S (0 disables cap),
#   TRAINING_MAX_STEPS (local default: 10000)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

API_PORT="${API_PORT:-8000}"
TERM_PORT="${TERM_PORT:-8001}"
FHIR_PORT="${FHIR_PORT:-8002}"
ANALYTICS_PORT="${ANALYTICS_PORT:-8003}"
MODEL_INFERENCE_PORT="${MODEL_INFERENCE_PORT:-8004}"
TRAINING_WORKER_PORT="${TRAINING_WORKER_PORT:-8005}"
PIPELINE_WORKER_PORT="${PIPELINE_WORKER_PORT:-8006}"
RESEARCH_WORKER_PORT="${RESEARCH_WORKER_PORT:-8007}"
UI_PORT="${UI_PORT:-3000}"
PIPELINE_WORKERS="${PIPELINE_WORKERS:-1}"
TERM_WORKERS="${TERM_WORKERS:-1}"
TRAINING_JOB_TIMEOUT_S="${TRAINING_JOB_TIMEOUT_S:-0}"
TRAINING_MAX_STEPS="${TRAINING_MAX_STEPS:-10000}"

SKIP_INSTALL=0
NO_WORKERS=0
NO_MODEL_INFERENCE=0
NO_TRAINING_WORKER=0
NO_RESEARCH_WORKER=0
SKIP_MCP_REGISTER=1
SERVICES_FILTER=""
E2E_MODE=0

usage() {
  sed -n '1,25p' "$0" | tail -n +2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-install) SKIP_INSTALL=1; shift ;;
    --no-workers) NO_WORKERS=1; shift ;;
    --no-model-inference) NO_MODEL_INFERENCE=1; shift ;;
    --no-training-worker) NO_TRAINING_WORKER=1; shift ;;
    --no-research-worker) NO_RESEARCH_WORKER=1; shift ;;
    --mcp) SKIP_MCP_REGISTER=0; shift ;;
    --no-mcp) SKIP_MCP_REGISTER=1; shift ;;
    --e2e) E2E_MODE=1; shift ;;
    --services)
      [[ $# -lt 2 ]] && usage
      SERVICES_FILTER="$2"
      shift 2
      ;;
    --api-port) API_PORT="$2"; shift 2 ;;
    --term-port) TERM_PORT="$2"; shift 2 ;;
    --fhir-port) FHIR_PORT="$2"; shift 2 ;;
    --analytics-port) ANALYTICS_PORT="$2"; shift 2 ;;
    --model-inference-port) MODEL_INFERENCE_PORT="$2"; shift 2 ;;
    --training-worker-port) TRAINING_WORKER_PORT="$2"; shift 2 ;;
    --pipeline-worker-port) PIPELINE_WORKER_PORT="$2"; shift 2 ;;
    --research-worker-port) RESEARCH_WORKER_PORT="$2"; shift 2 ;;
    --ui-port) UI_PORT="$2"; shift 2 ;;
    --pipeline-workers) PIPELINE_WORKERS="$2"; shift 2 ;;
    --term-workers) TERM_WORKERS="$2"; shift 2 ;;
    -h|--help) usage ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      ;;
  esac
done


python_major_minor() {
  "$1" -c 'import sys; print(sys.version_info[0] * 100 + sys.version_info[1])'
}

if [[ -n "${LEO_PYTHON:-}" ]]; then
  if [[ ! -x "$LEO_PYTHON" ]]; then
    echo "LEO_PYTHON is not an executable file: $LEO_PYTHON" >&2
    exit 1
  fi
  PY_BOOTSTRAP="$LEO_PYTHON"
elif command -v python3.12 >/dev/null 2>&1; then
  PY_BOOTSTRAP="$(command -v python3.12)"
else
  echo "Python 3.12 is required (matches CI). python3.12 was not found on PATH." >&2
  echo "Install it (example: brew install python@3.12), then either:" >&2
  echo "  PATH=\"\$(brew --prefix python@3.12)/bin:\$PATH\" ./scripts/start_leo-ai-core.sh" >&2
  echo "Or: export LEO_PYTHON=\"\$(brew --prefix python@3.12)/bin/python3.12\"" >&2
  exit 1
fi

py_mm="$(python_major_minor "$PY_BOOTSTRAP")"
if [[ "$py_mm" -ne 312 ]]; then
  echo "Bootstrap Python must be 3.12.x. Found: \"$PY_BOOTSTRAP\" $("$PY_BOOTSTRAP" -V 2>/dev/null)" >&2
  echo "Set LEO_PYTHON to a python3.12 binary or fix PATH so python3.12 is 3.12." >&2
  exit 1
fi

VENV_DIR="${REPO_ROOT}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
TRAINING_VENV_DIR="${REPO_ROOT}/.venv-training"
TRAINING_VENV_PYTHON="${TRAINING_VENV_DIR}/bin/python"
UI_DIR="${REPO_ROOT}/services/ui"
API_DIR="${REPO_ROOT}/services/api"
MODEL_INFERENCE_DIR="${REPO_ROOT}/services/model_inference"
TRAINING_WORKER_DIR="${REPO_ROOT}/services/training_worker"
RESEARCH_WORKER_DIR="${REPO_ROOT}/services/research_worker"
REQ_FILE="${REPO_ROOT}/requirements.txt"
API_REQ="${API_DIR}/requirements.txt"
MODEL_INFERENCE_REQ="${MODEL_INFERENCE_DIR}/requirements.txt"
PIPELINE_WORKER_REQ="${REPO_ROOT}/services/pipeline_worker/requirements.txt"
TERMINOLOGY_API_REQ="${REPO_ROOT}/services/terminology_api/requirements.txt"
FHIR_API_REQ="${REPO_ROOT}/services/fhir_api/requirements.txt"
ANALYTICS_API_REQ="${REPO_ROOT}/services/analytics_api/requirements.txt"
RESEARCH_WORKER_REQ="${RESEARCH_WORKER_DIR}/requirements.txt"
TRAINING_WORKER_REQ="${TRAINING_WORKER_DIR}/requirements.txt"
MODEL_CACHE_DIR="${REPO_ROOT}/.model_cache"

echo ""
echo "  LEO-AI-CORE - Local Dev Startup"
echo ""
echo "  [py]   Bootstrap interpreter: $($PY_BOOTSTRAP -V) ($PY_BOOTSTRAP)"

# Load .env-style files into this shell (export). Shared with Terminal launchers
# so Core API and UI use the same SDK_HOST_SHARED_SECRET.
# shellcheck source=scripts/lib/load_leo_dev_env.sh
source "${SCRIPT_DIR}/lib/load_leo_dev_env.sh"
import_dotenv() { _leo_import_dotenv "$@"; }

n="$(import_dotenv "${REPO_ROOT}/secrets/.env" 0)"
if [[ "$n" -gt 0 ]]; then echo "  [env]  Loaded $n vars from secrets/.env"; fi

n="$(import_dotenv "${REPO_ROOT}/secrets/.env.secrets" 0)"
if [[ "$n" -gt 0 ]]; then echo "  [env]  Loaded $n vars from secrets/.env.secrets"; fi

CONFIG_FILE="${REPO_ROOT}/secrets/.env.config"
n="$(import_dotenv "$CONFIG_FILE" 1)"
if [[ "$n" -gt 0 ]]; then
  echo "  [env]  Applied $n config vars from secrets/.env.config (override)"
else
  echo "  [env]  secrets/.env.config not found - using system env vars only."
fi

n="$(import_dotenv "${REPO_ROOT}/.env" 0)"
if [[ "$n" -gt 0 ]]; then echo "  [env]  Loaded $n vars from .env"; fi

if [[ "$SKIP_MCP_REGISTER" -eq 0 ]]; then
  MCP_JSON="${HOME}/.cursor/mcp.json"
  "$PY_BOOTSTRAP" "$SCRIPT_DIR/register_mcp.py" \
    --mcp-json "$MCP_JSON" \
    --name "user-leo-neo4j" \
    --cwd "$REPO_ROOT"
  echo "  [mcp]  Registered user-leo-neo4j in ${MCP_JSON} (leo-neo4j alias kept for compatibility)"
else
  echo "  [mcp]  Skipped user-leo-neo4j registration (--no-mcp)"
fi

if [[ -n "${AZURE_KEYVAULT_URL:-}" ]]; then
  echo "  [kv]   Key Vault in this shell: ${AZURE_KEYVAULT_URL}"
  echo "  [kv]   Unsetting it in service windows so they use secrets/.env.secrets"
  unset AZURE_KEYVAULT_URL
else
  echo "  [kv]   AZURE_KEYVAULT_URL not set - KV secret loading disabled."
fi
if [[ -z "${SESSION_KEY_NAMESPACE:-}" ]]; then
  export SESSION_KEY_NAMESPACE="dev"
fi
echo "  [auth] Session key namespace: ${SESSION_KEY_NAMESPACE}"
echo "  [accel] VECTOR_DEVICE=${VECTOR_DEVICE:-auto}  (MPS min macOS ${MPS_MIN_MACOS_MAJOR:-26})"
echo "  [accel] TRAINING_ACCELERATOR=${TRAINING_ACCELERATOR:-auto}  TRAINING_MPS_FAIL_FAST=${TRAINING_MPS_FAIL_FAST:-true}"
echo "  [accel] MODEL_INFERENCE_ACCELERATOR=${MODEL_INFERENCE_ACCELERATOR:-auto}  MODEL_INFERENCE_MPS_FAIL_FAST=${MODEL_INFERENCE_MPS_FAIL_FAST:-true}"

if [[ -z "${MODEL_REGISTRY_STORE:-}" ]]; then
  export MODEL_REGISTRY_STORE="neo4j"
fi
export MODEL_REGISTRY_STORE_PATH="${MODEL_CACHE_DIR}/model_registry.json"

if [[ ! -d "$MODEL_CACHE_DIR" ]]; then
  mkdir -p "$MODEL_CACHE_DIR"
  echo "  [dir]  Created .model_cache/ for NER model artifacts."
fi

if [[ -x "$VENV_PYTHON" ]]; then
  venv_mm="$(python_major_minor "$VENV_PYTHON")"
  if [[ "$venv_mm" -ne 312 ]]; then
    echo "  [venv] Existing .venv must be Python 3.12 (found ${venv_mm}, need 312). Recreate venvs:" >&2
    echo "    rm -rf \"$VENV_DIR\" \"$TRAINING_VENV_DIR\"" >&2
    exit 1
  fi
elif [[ ! -x "$VENV_PYTHON" ]]; then
  echo "  [venv] Creating shared virtual environment (.venv)..."
  "$PY_BOOTSTRAP" -m venv "$VENV_DIR"
  echo "  [venv] .venv created."
fi

if [[ "$NO_TRAINING_WORKER" -eq 0 ]]; then
  if [[ -x "$TRAINING_VENV_PYTHON" ]]; then
    tvm="$(python_major_minor "$TRAINING_VENV_PYTHON")"
    if [[ "$tvm" -ne 312 ]]; then
      echo "  [venv] .venv-training must be Python 3.12 (found ${tvm}). Remove it and re-run:" >&2
      echo "    rm -rf \"$TRAINING_VENV_DIR\"" >&2
      exit 1
    fi
  elif [[ ! -x "$TRAINING_VENV_PYTHON" ]]; then
    echo "  [venv] Creating training worker virtual environment (.venv-training)..."
    "$PY_BOOTSTRAP" -m venv "$TRAINING_VENV_DIR"
    echo "  [venv] .venv-training created."
  fi
fi

if [[ "$SKIP_INSTALL" -eq 0 ]]; then
  echo "  [pip]  Installing / upgrading shared Python dependencies..."
  "$VENV_PYTHON" -m pip install --quiet --upgrade pip
  "$VENV_PYTHON" -m pip install --quiet --upgrade -r "$REQ_FILE"
  if [[ -f "$API_REQ" ]]; then
    "$VENV_PYTHON" -m pip install --quiet --upgrade -r "$API_REQ"
  fi
  if [[ -f "$MODEL_INFERENCE_REQ" ]]; then
    "$VENV_PYTHON" -m pip install --quiet --upgrade -r "$MODEL_INFERENCE_REQ"
  fi
  for extra in "$PIPELINE_WORKER_REQ" "$TERMINOLOGY_API_REQ" "$FHIR_API_REQ" "$ANALYTICS_API_REQ" "$RESEARCH_WORKER_REQ"; do
    if [[ -f "$extra" ]]; then
      "$VENV_PYTHON" -m pip install --quiet --upgrade -r "$extra"
    fi
  done
  echo "  [pip]  Shared Python dependencies up to date."

  if [[ "$NO_TRAINING_WORKER" -eq 0 && -f "$TRAINING_WORKER_REQ" ]]; then
    echo "  [pip]  Installing training worker dependencies (.venv-training)..."
    "$TRAINING_VENV_PYTHON" -m pip install --quiet --upgrade pip
    "$TRAINING_VENV_PYTHON" -m pip install --quiet --upgrade -r "$TRAINING_WORKER_REQ"
    echo "  [pip]  Training worker dependencies up to date."
  fi
else
  if [[ "$NO_TRAINING_WORKER" -eq 0 && -f "$TRAINING_WORKER_REQ" && ! -x "$TRAINING_VENV_PYTHON" ]]; then
    echo "  [venv] Creating training worker virtual environment (.venv-training)..."
    "$PY_BOOTSTRAP" -m venv "$TRAINING_VENV_DIR"
    echo "  [pip]  Installing training worker dependencies (.venv-training)..."
    "$TRAINING_VENV_PYTHON" -m pip install --quiet --upgrade pip
    "$TRAINING_VENV_PYTHON" -m pip install --quiet --upgrade -r "$TRAINING_WORKER_REQ"
  fi
fi

if [[ "$SKIP_INSTALL" -eq 0 ]]; then
  echo "  [npm]  Installing / updating UI dependencies..."
  (cd "$UI_DIR" && npm install --silent)
  echo "  [npm]  UI dependencies up to date."
elif [[ ! -d "${UI_DIR}/node_modules" ]]; then
  echo "  [npm]  node_modules missing - running npm install..."
  (cd "$UI_DIR" && npm install --silent)
  echo "  [npm]  UI dependencies installed."
fi

should_start() {
  local name="$1"
  if [[ -z "$SERVICES_FILTER" ]]; then
    return 0
  fi
  local IFS=,
  local s
  for s in $SERVICES_FILTER; do
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    if [[ "$s" == "$name" ]]; then
      return 0
    fi
  done
  return 1
}

# macOS: open a new Terminal.app window running a generated launcher script.
# Args: title, inner_command, [workdir defaults to REPO_ROOT]
start_service_window() {
  local title="$1"
  local inner_cmd="$2"
  local workdir="${3:-$REPO_ROOT}"
  local launcher
  launcher="$(mktemp "${TMPDIR:-/tmp}/leo-ai-core-launcher.XXXXXX")"
  {
    echo '#!/usr/bin/env bash'
    printf '# %s\n' "$title"
    printf 'cd %q\n' "$workdir"
    # Force a friendly terminal title for this service tab/window.
    printf 'printf %q\n' $'\033]0;'"${title}"$'\007\033]1;'"${title}"$'\007'
    printf 'export PYTHONPATH=%q\n' "$REPO_ROOT"
    # Re-load secrets into THIS Terminal window. macOS Terminal "do script"
    # does not inherit exports from the start script process, which previously
    # left Core API on a stale SDK_HOST_SHARED_SECRET while the UI minted
    # tokens with SCENARIO_SDK_HOST_SECRET from services/ui/.env.local.
    printf 'export LEO_REPO_ROOT=%q\n' "$REPO_ROOT"
    printf '# shellcheck disable=SC1091\n'
    printf 'source %q\n' "${SCRIPT_DIR}/lib/load_leo_dev_env.sh"
    # Local start uses secrets/.env.secrets. A shell-level Atlas vault
    # URL would force Key Vault and abort when those LEO secrets are
    # not in that vault.
    printf 'unset AZURE_KEYVAULT_URL\n'
    if [[ -n "${TERMINOLOGY_API_URLS:-}" ]]; then
      printf 'export TERMINOLOGY_API_URLS=%q\n' "$TERMINOLOGY_API_URLS"
    fi
    printf 'exec bash -c %q\n' "$inner_cmd"
  } > "$launcher"
  chmod +x "$launcher"
  if [[ "$(uname -s)" == "Darwin" ]]; then
    osascript <<OSA >/dev/null
set launcherPath to "$launcher"
set windowTitle to "$title"
tell application "Terminal"
  activate
  set newTab to do script quoted form of launcherPath
  delay 0.3
  set custom title of newTab to windowTitle
end tell
OSA
  else
    echo "  [note] Non-macOS: starting in background: $title"
    bash "$launcher" &
  fi
}

kill_listener_on_port() {
  local port="$1"
  local label="${2:-port ${port}}"
  local pids
  pids="$(lsof -ti TCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
    echo "    ${label}  [freed port ${port}]"
    sleep 2
  fi
}

TERMINOLOGY_API_URLS=""
WINDOW_COUNT=0

echo ""
echo "  Starting services..."

if should_start "api"; then
  # localhost:8000 must be Core API. A 127.0.0.1 bind from another repo
  # wins on macOS and Validation Lab then returns a bare "Not Found".
  kill_listener_on_port "$API_PORT" "Core API"
  start_service_window "Core API :${API_PORT}" \
    "'$VENV_PYTHON' -m uvicorn app.main:app --app-dir '$API_DIR' --reload --reload-dir services/api --reload-dir libs --host 0.0.0.0 --port $API_PORT"
  echo "    Core API           http://localhost:${API_PORT}"
  WINDOW_COUNT=$((WINDOW_COUNT + 1))
fi

if should_start "terminology_api"; then
  term_urls=()
  for ((t = 0; t < TERM_WORKERS; t++)); do
    t_port=$((TERM_PORT + t * 10))
    term_urls+=("http://localhost:${t_port}")
    if [[ "$t" -eq 0 ]]; then
      term_cmd="'$VENV_PYTHON' -m uvicorn services.terminology_api.app.main:app --reload --reload-dir services/terminology_api --reload-dir libs --host 0.0.0.0 --port $t_port"
      start_service_window "Terminology API :${t_port}" "$term_cmd"
      echo "    Terminology API    http://localhost:${t_port} (primary)"
    else
      term_cmd="'$VENV_PYTHON' -m uvicorn services.terminology_api.app.main:app --workers 4 --host 0.0.0.0 --port $t_port"
      start_service_window "Terminology API :${t_port}" "$term_cmd"
      echo "    Terminology API    http://localhost:${t_port} (worker $t)"
    fi
    WINDOW_COUNT=$((WINDOW_COUNT + 1))
  done
  TERMINOLOGY_API_URLS=$(IFS=,; echo "${term_urls[*]}")
  export TERMINOLOGY_API_URLS
  if [[ "$TERM_WORKERS" -gt 1 ]]; then
    echo "    TERMINOLOGY_API_URLS=${TERMINOLOGY_API_URLS}"
  fi
fi

if should_start "fhir_api"; then
  start_service_window "FHIR API :${FHIR_PORT}" \
    "'$VENV_PYTHON' -m uvicorn services.fhir_api.app.main:app --reload --reload-dir services/fhir_api --reload-dir libs --host 0.0.0.0 --port $FHIR_PORT"
  echo "    FHIR API           http://localhost:${FHIR_PORT}"
  WINDOW_COUNT=$((WINDOW_COUNT + 1))
fi

if should_start "analytics_api"; then
  start_service_window "Analytics API :${ANALYTICS_PORT}" \
    "'$VENV_PYTHON' -m uvicorn services.analytics_api.app.main:app --reload --reload-dir services/analytics_api --reload-dir libs --host 0.0.0.0 --port $ANALYTICS_PORT"
  echo "    Analytics API      http://localhost:${ANALYTICS_PORT}"
  WINDOW_COUNT=$((WINDOW_COUNT + 1))
fi

if [[ "$NO_MODEL_INFERENCE" -eq 0 ]] && should_start "model_inference"; then
  start_service_window "Model Inference :${MODEL_INFERENCE_PORT}" \
    "'$VENV_PYTHON' -m uvicorn app.main:app --app-dir '$MODEL_INFERENCE_DIR' --host 0.0.0.0 --port $MODEL_INFERENCE_PORT"
  echo "    Model Inference    http://localhost:${MODEL_INFERENCE_PORT}  (NER /extract /health /reload /versions)"
  WINDOW_COUNT=$((WINDOW_COUNT + 1))
else
  echo "    Model Inference    [skipped; omit --no-model-inference to start]"
fi

if [[ "$NO_TRAINING_WORKER" -eq 0 ]] && should_start "training_worker"; then
  kill_listener_on_port "$TRAINING_WORKER_PORT" "Training Worker"
  start_service_window "Training Worker :${TRAINING_WORKER_PORT}" \
    "TRAINING_JOB_TIMEOUT_S='$TRAINING_JOB_TIMEOUT_S' TRAINING_MAX_STEPS='$TRAINING_MAX_STEPS' '$TRAINING_VENV_PYTHON' -m uvicorn app.main:app --app-dir '$TRAINING_WORKER_DIR' --host 0.0.0.0 --port $TRAINING_WORKER_PORT"
  echo "    Training Worker    http://localhost:${TRAINING_WORKER_PORT}  (NER fine-tuning /train/jobs /train/progress, timeout=${TRAINING_JOB_TIMEOUT_S}s, max_steps=${TRAINING_MAX_STEPS})"
  WINDOW_COUNT=$((WINDOW_COUNT + 1))
else
  echo "    Training Worker    [skipped; omit --no-training-worker to start]"
fi

if [[ "$NO_RESEARCH_WORKER" -eq 0 ]] && should_start "research_worker"; then
  start_service_window "Research Worker :${RESEARCH_WORKER_PORT}" \
    "'$VENV_PYTHON' -m uvicorn services.research_worker.app.main:app --reload --reload-dir services/research_worker --reload-dir services/analytics_api --reload-dir libs --host 0.0.0.0 --port $RESEARCH_WORKER_PORT"
  echo "    Research Worker    http://localhost:${RESEARCH_WORKER_PORT}  (Pathway Explorer /research/jobs)"
  WINDOW_COUNT=$((WINDOW_COUNT + 1))
else
  echo "    Research Worker    [skipped; omit --no-research-worker to start]"
fi

if [[ "$NO_WORKERS" -eq 0 ]] && should_start "pipeline_worker"; then
  # Skip ports reserved by other local services (research defaults to 8007).
  # Friendly agent names match services/ui validation-lab agentRoster.ts.
  pipeline_agent_names=(
    Ada Curie Nightingale Faraday Turing Lovelace
    Pasteur Jenner Hodgkin Seacole Fleming Darwin
  )
  reserved_ports=("$RESEARCH_WORKER_PORT" "$TRAINING_WORKER_PORT" "$UI_PORT")
  worker_port=$PIPELINE_WORKER_PORT
  pipeline_ports=()
  for ((i = 1; i <= PIPELINE_WORKERS; i++)); do
    while true; do
      skip=0
      for reserved in "${reserved_ports[@]}"; do
        if [[ "$worker_port" -eq "$reserved" ]]; then
          skip=1
          break
        fi
      done
      if [[ "$skip" -eq 0 ]]; then
        break
      fi
      worker_port=$((worker_port + 1))
    done
    pipeline_ports+=("$worker_port")
    agent_idx=$(( (i - 1) % ${#pipeline_agent_names[@]} ))
    agent_name="${pipeline_agent_names[$agent_idx]}"
    kill_listener_on_port "$worker_port" "Pipeline Worker ${agent_name}"
    start_service_window "Pipeline Worker ${agent_name} :${worker_port}" \
      "export PIPELINE_WORKER_PORT='${worker_port}'; export PIPELINE_WORKER_NAME='${agent_name}'; '$VENV_PYTHON' -m uvicorn services.pipeline_worker.app.main:app --reload --reload-dir services/pipeline_worker --reload-dir libs --host 0.0.0.0 --port ${worker_port} --log-level info"
    worker_port=$((worker_port + 1))
  done
  echo "    Pipeline Workers   (x${PIPELINE_WORKERS} - HTTP :${pipeline_ports[*]} + message bus)"
  WINDOW_COUNT=$((WINDOW_COUNT + PIPELINE_WORKERS))
fi

if should_start "ui"; then
  if [[ "$E2E_MODE" -eq 1 ]]; then
    ui_cmd="NEXT_PUBLIC_E2E_MODE=true npm run dev -- --port $UI_PORT"
    echo "    UI                 http://localhost:${UI_PORT}  [E2E mode - mock session active]"
  else
    ui_cmd="npm run dev -- --port $UI_PORT"
    echo "    UI                 http://localhost:${UI_PORT}"
  fi
  start_service_window "UI :${UI_PORT}" "$ui_cmd" "$UI_DIR"
  WINDOW_COUNT=$((WINDOW_COUNT + 1))
fi

echo ""
if [[ "$(uname -s)" == "Darwin" ]]; then
  echo "  ${WINDOW_COUNT} Terminal window(s) opened. Close them to stop services."
else
  echo "  ${WINDOW_COUNT} background service(s) started from this shell."
fi
if [[ "$TERM_WORKERS" -gt 1 ]]; then
  echo "  Terminology API running on ${TERM_WORKERS} instances. TERMINOLOGY_API_URLS is exported for round-robin."
  echo "  To run the evaluation script against all instances:"
  echo "    .venv/bin/python -m scripts.evaluate_training_data"
fi
echo ""
