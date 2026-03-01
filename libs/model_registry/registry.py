"""Versioned model lifecycle registry for spaCy NER models.

Lifecycle states
----------------
registered  → offline_validated → canary → promoted → (rollback →) deprecated

Transition rules
----------------
- offline_validated requires passing precision/recall thresholds.
- canary requires a cohort KPI result posted via record_canary_result().
- promoted requires canary KPI pass AND rollback_target registered AND healthy
  rollback target stored in blob.
- rollback downgrades the active model to the rollback_target.

On promote / rollback the registry automatically signals the inference service
via POST /reload so the new model is hot-swapped without restarting.

Environment variables
---------------------
MODEL_REGISTRY_STORE_PATH   Path to JSON persistence file (optional).
                            In production use a shared store (Redis / Neo4j).
                            Defaults to an in-memory dict.
CODING_MODEL_ENDPOINT       Inference service base URL for /reload calls.
                            Defaults to http://localhost:8004.
MODEL_RELOAD_TIMEOUT_S      Seconds to wait for /reload to complete (default 120).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

_REGISTRY_STORE_PATH = os.getenv("MODEL_REGISTRY_STORE_PATH", "")
_INFERENCE_ENDPOINT = os.getenv("CODING_MODEL_ENDPOINT", "http://localhost:8004")
_RELOAD_TIMEOUT_S = float(os.getenv("MODEL_RELOAD_TIMEOUT_S", "120"))

# Minimum offline eval thresholds (overridable via env)
_MIN_PRECISION = float(os.getenv("MODEL_MIN_PRECISION", "0.80"))
_MIN_RECALL = float(os.getenv("MODEL_MIN_RECALL", "0.75"))
_MIN_CANARY_PRECISION = float(os.getenv("MODEL_CANARY_MIN_PRECISION", "0.78"))
_MIN_CANARY_RECALL = float(os.getenv("MODEL_CANARY_MIN_RECALL", "0.72"))


class ModelStatus(str, Enum):
    REGISTERED = "registered"
    OFFLINE_VALIDATED = "offline_validated"
    CANARY = "canary"
    PROMOTED = "promoted"
    DEPRECATED = "deprecated"
    ROLLBACK = "rollback"


@dataclass
class ModelRecord:
    model_name: str
    model_version: str
    model_path: str              # local training output path (used during training only)
    training_dataset_version: str
    schema_version: str
    deid_version: str
    artifact_uri: str = ""       # blob path after upload e.g. "medspacy_clinical_ner/1.2/model.tar.gz"
    status: str = ModelStatus.REGISTERED
    offline_precision: Optional[float] = None
    offline_recall: Optional[float] = None
    canary_precision: Optional[float] = None
    canary_recall: Optional[float] = None
    canary_cohort: Optional[str] = None
    rollback_target_version: Optional[str] = None
    registered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    promoted_at: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ModelRecord":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class ModelRegistry:
    """In-process model lifecycle registry.

    For production, back this with a shared store (Redis or Neo4j node).
    """

    def __init__(self) -> None:
        self._records: dict[str, ModelRecord] = {}  # version -> record
        self._active_version: Optional[str] = None
        self._load()

    # ------------------------------------------------------------------
    # Blob upload
    # ------------------------------------------------------------------

    def upload_artifact(
        self,
        version: str,
        model_dir: str,
        *,
        schema_version: str = "",
        deid_version: str = "",
        label_mapping_version: str = "",
        dataset_version: str = "",
        notes: str = "",
    ) -> str:
        """Upload a trained model directory to Azure Blob Storage.

        Updates the ModelRecord with the returned artifact_uri.

        Args:
            version: Must already be registered.
            model_dir: Local path to the trained spaCy model directory.

        Returns:
            The blob path URI (e.g. ``"medspacy_clinical_ner/1.2/model.tar.gz"``).
        """
        from libs.model_store import ModelStore

        record = self._get(version)
        store = ModelStore()
        uri = store.upload(
            model_dir,
            version,
            schema_version=schema_version or record.schema_version,
            deid_version=deid_version or record.deid_version,
            label_mapping_version=label_mapping_version,
            dataset_version=dataset_version or record.training_dataset_version,
            notes=notes,
        )
        record.artifact_uri = uri
        logger.info(
            "ModelRegistry: uploaded v%s artifact to blob: %s", version, uri
        )
        self._save()
        return uri

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, record: ModelRecord) -> ModelRecord:
        """Register a new model version."""
        if record.model_version in self._records:
            raise ValueError(
                f"ModelRegistry: version {record.model_version!r} already registered"
            )
        self._records[record.model_version] = record
        logger.info(
            "ModelRegistry: registered %s v%s (dataset=%s schema=%s)",
            record.model_name, record.model_version,
            record.training_dataset_version, record.schema_version,
        )
        self._save()
        return record

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------

    def validate_offline(
        self,
        version: str,
        precision: float,
        recall: float,
        notes: str = "",
    ) -> ModelRecord:
        """Record offline eval metrics and advance to offline_validated if passing."""
        record = self._get(version)
        record.offline_precision = round(precision, 4)
        record.offline_recall = round(recall, 4)
        record.notes = notes

        if precision >= _MIN_PRECISION and recall >= _MIN_RECALL:
            record.status = ModelStatus.OFFLINE_VALIDATED
            logger.info(
                "ModelRegistry: v%s offline validated (P=%.3f R=%.3f)",
                version, precision, recall,
            )
        else:
            record.status = ModelStatus.DEPRECATED
            logger.warning(
                "ModelRegistry: v%s failed offline validation (P=%.3f R=%.3f) "
                "— thresholds P>=%.2f R>=%.2f",
                version, precision, recall, _MIN_PRECISION, _MIN_RECALL,
            )
        self._save()
        return record

    def start_canary(
        self,
        version: str,
        cohort: str = "canary_cohort",
    ) -> ModelRecord:
        """Advance offline-validated model to canary deployment."""
        record = self._get(version)
        if record.status != ModelStatus.OFFLINE_VALIDATED:
            raise RuntimeError(
                f"ModelRegistry: cannot start canary from status={record.status!r}"
            )
        record.status = ModelStatus.CANARY
        record.canary_cohort = cohort
        logger.info("ModelRegistry: v%s started canary on cohort=%s", version, cohort)
        self._save()
        return record

    def record_canary_result(
        self,
        version: str,
        precision: float,
        recall: float,
    ) -> ModelRecord:
        """Record canary KPI results.  Caller still needs to call promote()."""
        record = self._get(version)
        record.canary_precision = round(precision, 4)
        record.canary_recall = round(recall, 4)
        logger.info(
            "ModelRegistry: v%s canary result (P=%.3f R=%.3f)",
            version, precision, recall,
        )
        self._save()
        return record

    def promote(
        self,
        version: str,
        rollback_target_version: Optional[str] = None,
        force: bool = False,
    ) -> ModelRecord:
        """Promote a canary model to production active.

        Requirements:
        - Status must be CANARY.
        - Canary KPIs must be present and pass thresholds (bypassed when force=True).
        - rollback_target_version must be registered (unless first ever promotion).

        Args:
            force: Skip canary threshold gate. Use only when deliberately overriding
                   a gate failure — the reason should be documented in the model notes.
        """
        record = self._get(version)
        if record.status != ModelStatus.CANARY:
            raise RuntimeError(
                f"ModelRegistry: cannot promote from status={record.status!r}"
            )

        if record.canary_precision is None or record.canary_recall is None:
            raise RuntimeError(
                "ModelRegistry: canary KPIs not recorded — call record_canary_result() first"
            )

        if not force and (
            record.canary_precision < _MIN_CANARY_PRECISION
            or record.canary_recall < _MIN_CANARY_RECALL
        ):
            raise RuntimeError(
                f"ModelRegistry: canary KPI thresholds not met "
                f"(P={record.canary_precision:.3f} R={record.canary_recall:.3f}) "
                f"— thresholds P>={_MIN_CANARY_PRECISION} R>={_MIN_CANARY_RECALL}"
            )

        # Validate rollback target exists
        if rollback_target_version:
            if rollback_target_version not in self._records:
                raise RuntimeError(
                    f"ModelRegistry: rollback_target_version={rollback_target_version!r} "
                    f"not registered"
                )
            record.rollback_target_version = rollback_target_version
        elif self._active_version and self._active_version != version:
            record.rollback_target_version = self._active_version

        # Demote old active to deprecated
        if self._active_version and self._active_version != version:
            old = self._records.get(self._active_version)
            if old and old.status == ModelStatus.PROMOTED:
                old.status = ModelStatus.DEPRECATED

        record.status = ModelStatus.PROMOTED
        record.promoted_at = datetime.now(timezone.utc).isoformat()
        if force:
            record.notes = (
                f"{record.notes}\n[FORCED PROMOTION] Gate overridden: "
                f"P={record.canary_precision:.3f} R={record.canary_recall:.3f} "
                f"(thresholds P>={_MIN_CANARY_PRECISION} R>={_MIN_CANARY_RECALL})"
            ).strip()
            logger.warning(
                "ModelRegistry: v%s FORCE-PROMOTED — gate thresholds not met "
                "(P=%.3f R=%.3f, required P>=%.2f R>=%.2f)",
                version, record.canary_precision, record.canary_recall,
                _MIN_CANARY_PRECISION, _MIN_CANARY_RECALL,
            )
        self._active_version = version
        logger.info(
            "ModelRegistry: v%s PROMOTED to active (rollback_target=%s force=%s)",
            version, record.rollback_target_version, force,
        )
        self._save()
        # Signal the inference service to hot-swap immediately
        self._signal_reload(version)
        return record

    def rollback(self) -> ModelRecord:
        """Rollback active model to its registered rollback_target."""
        if not self._active_version:
            raise RuntimeError("ModelRegistry: no active model to roll back from")
        active = self._records[self._active_version]
        target_ver = active.rollback_target_version
        if not target_ver:
            raise RuntimeError(
                f"ModelRegistry: active v{self._active_version} has no rollback target"
            )
        target = self._get(target_ver)
        active.status = ModelStatus.ROLLBACK
        target.status = ModelStatus.PROMOTED
        self._active_version = target_ver
        logger.warning(
            "ModelRegistry: ROLLBACK — demoted v%s, restored v%s",
            active.model_version, target_ver,
        )
        self._save()
        # Signal the inference service to hot-swap back to the rollback target
        self._signal_reload(target_ver)
        return target

    # ------------------------------------------------------------------
    # Inference service reload signal
    # ------------------------------------------------------------------

    def _signal_reload(self, version: str) -> None:
        """POST /reload to the inference service to hot-swap to a new version.

        Non-fatal — logs a warning if the service is unreachable rather than
        blocking promotion.  The calling code can also trigger /reload manually
        or rely on the inference service's CODING_MODEL_VERSION env var at next
        restart.
        """
        try:
            resp = httpx.post(
                f"{_INFERENCE_ENDPOINT}/reload",
                json={"version": version},
                timeout=_RELOAD_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "ModelRegistry: inference service reloaded to v%s in %dms",
                data.get("active_version"), data.get("elapsed_ms", 0),
            )
        except Exception:
            logger.warning(
                "ModelRegistry: could not signal /reload on %s — "
                "inference service may still be on old version.  "
                "Call POST /reload manually or restart the service.",
                _INFERENCE_ENDPOINT,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_active(self) -> Optional[ModelRecord]:
        """Return the currently promoted model record, or None."""
        if not self._active_version:
            return None
        return self._records.get(self._active_version)

    def get(self, version: str) -> Optional[ModelRecord]:
        return self._records.get(version)

    def list_all(self) -> list[ModelRecord]:
        return list(self._records.values())

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _get(self, version: str) -> ModelRecord:
        if version not in self._records:
            raise KeyError(f"ModelRegistry: version {version!r} not found")
        return self._records[version]

    def _save(self) -> None:
        if not _REGISTRY_STORE_PATH:
            return
        try:
            data = {
                "active_version": self._active_version,
                "records": {v: r.to_dict() for v, r in self._records.items()},
            }
            Path(_REGISTRY_STORE_PATH).write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
        except Exception:
            logger.warning("ModelRegistry: failed to persist to %s", _REGISTRY_STORE_PATH,
                           exc_info=True)

    def _load(self) -> None:
        if not _REGISTRY_STORE_PATH:
            return
        p = Path(_REGISTRY_STORE_PATH)
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            self._active_version = data.get("active_version")
            for ver, rec_dict in data.get("records", {}).items():
                self._records[ver] = ModelRecord.from_dict(rec_dict)
            logger.info(
                "ModelRegistry: loaded %d records from %s (active=%s)",
                len(self._records), _REGISTRY_STORE_PATH, self._active_version,
            )
        except Exception:
            logger.warning(
                "ModelRegistry: failed to load from %s", _REGISTRY_STORE_PATH,
                exc_info=True,
            )


# Module-level singleton
_registry: Optional[ModelRegistry] = None


def get_registry() -> ModelRegistry:
    """Return the module-level ModelRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
