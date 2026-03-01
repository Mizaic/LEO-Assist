"""One-off script to register a model that was successfully uploaded to Azure Blob
but failed at the registry step due to the now-fixed TypeError bug.

Usage (from repo root, with .venv active):
    python scripts/recover_model_registration.py

Edit the constants below to match the failed run's logs before running.
"""

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Fill these in from the training logs of the failed run
# ---------------------------------------------------------------------------
VERSION         = "20260301-025308"   # timestamp from "uploaded .../20260301-025308/..."
ARTIFACT_URI    = "medspacy_clinical_ner/20260301-025308/model.tar.gz"
OFFLINE_P       = 0.952               # from "Results: P=0.952"
OFFLINE_R       = 0.954               # from "Results: R=0.954"
OFFLINE_F1      = 0.953               # from "Results: F1=0.953"
DEV_DOC_COUNT   = 2532               # from "Evaluating on 2532 dev documents"
TRAIN_COUNT     = 0                   # set if known from export logs
DEV_COUNT       = 0                   # set if known from export logs
TRIGGERED_BY    = "manual-recovery"
NOTES           = "Registered via recovery script — training ran 2026-03-01, registry step failed due to pre-fix TypeError"
# ---------------------------------------------------------------------------

# Add repo root and services to path so libs resolve
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "training_worker"))

# Load .env so env vars (MODEL_REGISTRY_STORE_PATH, etc.) are set
env_path = REPO_ROOT / "secrets" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())
    print(f"Loaded env from {env_path}")
else:
    print(f"WARNING: {env_path} not found — ensure MODEL_REGISTRY_STORE_PATH is set manually")

store_path = os.getenv("MODEL_REGISTRY_STORE_PATH", "")
print(f"MODEL_REGISTRY_STORE_PATH = {store_path!r}")

from libs.model_registry.registry import ModelRecord, ModelRegistry  # noqa: E402

record = ModelRecord(
    model_name=os.getenv("MODEL_STORE_MODEL_NAME", "medspacy_clinical_ner"),
    model_version=VERSION,
    model_path="",
    training_dataset_version="",
    schema_version=os.getenv("MODEL_REQUIRED_SCHEMA_VERSION", "1.0"),
    deid_version=os.getenv("MODEL_REQUIRED_DEID_VERSION", "1.0"),
    artifact_uri=ARTIFACT_URI,
    notes=json.dumps({
        "triggered_by": TRIGGERED_BY,
        "base_model": os.getenv("TRAINING_HF_BASE_MODEL", "emilyalsentzer/Bio_ClinicalBERT"),
        "offline_f1": OFFLINE_F1,
        "offline_precision": OFFLINE_P,
        "offline_recall": OFFLINE_R,
        "dev_doc_count": DEV_DOC_COUNT,
        "train_count": TRAIN_COUNT,
        "dev_count": DEV_COUNT,
        "gate_min_precision": float(os.getenv("MODEL_MIN_PRECISION", "0.80")),
        "gate_min_recall": float(os.getenv("MODEL_MIN_RECALL", "0.75")),
        "gate_passed": True,
        "recovery": True,
        "user_notes": NOTES,
    }),
)

registry = ModelRegistry()

# Guard: don't double-register if the script is run twice
existing = registry.get(VERSION)
if existing:
    print(f"Version {VERSION} already registered with status={existing.status!r}. Nothing to do.")
    sys.exit(0)

registry.register(record)
registry.validate_offline(version=VERSION, precision=OFFLINE_P, recall=OFFLINE_R)

result = registry.get(VERSION)
print()
print(f"Successfully registered version {VERSION}")
print(f"  status          : {result.status}")
print(f"  artifact_uri    : {result.artifact_uri}")
print(f"  offline_precision: {result.offline_precision}")
print(f"  offline_recall  : {result.offline_recall}")
print(f"  registered_at   : {result.registered_at}")
if store_path:
    print(f"  persisted to    : {store_path}")
else:
    print("  WARNING: MODEL_REGISTRY_STORE_PATH not set — record is in-memory only!")
    print("  Set MODEL_REGISTRY_STORE_PATH in secrets/.env and re-run.")
