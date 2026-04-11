"""Neo4j-backed model registry. Stores model manifests in the Knowledge Graph.

Use when MODEL_REGISTRY_STORE=neo4j. The registry reads/writes (:ModelVersion)
nodes and a (:ModelRegistryConfig {id: 'default'}) singleton for active_version.

Environment variables
---------------------
MODEL_REGISTRY_STORE                    "neo4j" to use this backend; "json" or unset for file-based.
KNOWLEDGE_GRAPH_NEO4J_URI               Knowledge Graph credentials (model registry lives here,
KNOWLEDGE_GRAPH_NEO4J_USERNAME          not in the Patient Graph — model versions are AI system
KNOWLEDGE_GRAPH_NEO4J_PASSWORD          config, not patient data).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from libs.model_registry.registry import (
    ModelRecord,
    ModelStatus,
    _MIN_CANARY_PRECISION,
    _MIN_CANARY_RECALL,
    _MIN_PRECISION,
    _MIN_RECALL,
)

logger = logging.getLogger(__name__)


def _null_to_empty(v: Any) -> str:
    return "" if v is None else str(v)


def _row_to_record(row: dict[str, Any]) -> ModelRecord:
    return ModelRecord(
        model_name=_null_to_empty(row.get("model_name")),
        model_version=_null_to_empty(row.get("model_version")),
        model_path=_null_to_empty(row.get("model_path")),
        training_dataset_version=_null_to_empty(row.get("training_dataset_version")),
        schema_version=_null_to_empty(row.get("schema_version")),
        deid_version=_null_to_empty(row.get("deid_version")),
        artifact_uri=_null_to_empty(row.get("artifact_uri")),
        status=row.get("status") or ModelStatus.REGISTERED,
        offline_precision=row.get("offline_precision"),
        offline_recall=row.get("offline_recall"),
        canary_precision=row.get("canary_precision"),
        canary_recall=row.get("canary_recall"),
        canary_cohort=row.get("canary_cohort"),
        rollback_target_version=row.get("rollback_target_version"),
        registered_at=row.get("registered_at")
        or datetime.now(timezone.utc).isoformat(),
        promoted_at=row.get("promoted_at"),
        notes=_null_to_empty(row.get("notes")),
    )


def _record_to_params(rec: ModelRecord) -> dict[str, Any]:
    return {
        "model_name": rec.model_name,
        "model_path": rec.model_path,
        "training_dataset_version": rec.training_dataset_version,
        "schema_version": rec.schema_version,
        "deid_version": rec.deid_version,
        "artifact_uri": rec.artifact_uri,
        "status": rec.status,
        "offline_precision": rec.offline_precision,
        "offline_recall": rec.offline_recall,
        "canary_precision": rec.canary_precision,
        "canary_recall": rec.canary_recall,
        "canary_cohort": rec.canary_cohort,
        "rollback_target_version": rec.rollback_target_version,
        "registered_at": rec.registered_at,
        "promoted_at": rec.promoted_at,
        "notes": rec.notes,
    }


class Neo4jModelRegistry:
    """Model registry backed by Neo4j Patient Graph."""

    def __init__(self) -> None:
        from libs.neo4j_client.client import KnowledgeGraphClient

        self._client = KnowledgeGraphClient()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        from libs.cypher.schema_constraints import PATIENT_SCHEMA_CONSTRAINTS

        model_constraints = [
            c
            for c in PATIENT_SCHEMA_CONSTRAINTS
            if "ModelVersion" in c or "ModelRegistryConfig" in c
        ]
        for q in model_constraints:
            try:
                self._client.run(q)
            except Exception:
                logger.debug("Constraint may already exist: %s", q[:60])

    def _get_client(self):
        return self._client

    def _get(self, version: str) -> ModelRecord:
        from libs.cypher.model_registry_queries import GET_MODEL_VERSION

        rows = self._client.run(GET_MODEL_VERSION, version=version)
        if not rows:
            raise KeyError(f"ModelRegistry: version {version!r} not found")
        return _row_to_record(rows[0])

    def _save_record(self, rec: ModelRecord) -> None:
        from libs.cypher.model_registry_queries import CREATE_MODEL_VERSION

        params = {"version": rec.model_version, **_record_to_params(rec)}
        self._client.run(CREATE_MODEL_VERSION, **params)

    def _update_record(self, version: str, updates: dict[str, Any]) -> None:
        from libs.cypher.model_registry_queries import UPDATE_MODEL_VERSION

        self._client.run(UPDATE_MODEL_VERSION, version=version, updates=updates)

    def _get_active_version(self) -> Optional[str]:
        from libs.cypher.model_registry_queries import GET_ACTIVE_VERSION

        rows = self._client.run(GET_ACTIVE_VERSION)
        if not rows:
            return None
        return rows[0].get("active_version")

    def _set_active_version(self, version: Optional[str]) -> None:
        from libs.cypher.model_registry_queries import SET_ACTIVE_VERSION

        self._client.run(SET_ACTIVE_VERSION, active_version=version)

    # ------------------------------------------------------------------
    # Blob upload (delegates to ModelStore; updates record in Neo4j)
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
        self._update_record(version, {"artifact_uri": uri})
        logger.info("ModelRegistry: uploaded v%s artifact to blob: %s", version, uri)
        return uri

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, record: ModelRecord) -> ModelRecord:
        existing = self.get(record.model_version)
        if existing:
            raise ValueError(
                f"ModelRegistry: version {record.model_version!r} already registered"
            )
        self._save_record(record)
        logger.info(
            "ModelRegistry: registered %s v%s (dataset=%s schema=%s)",
            record.model_name,
            record.model_version,
            record.training_dataset_version,
            record.schema_version,
        )
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
        record = self._get(version)
        record.offline_precision = round(precision, 4)
        record.offline_recall = round(recall, 4)
        record.notes = notes

        if precision >= _MIN_PRECISION and recall >= _MIN_RECALL:
            record.status = ModelStatus.OFFLINE_VALIDATED
            logger.info(
                "ModelRegistry: v%s offline validated (P=%.3f R=%.3f)",
                version,
                precision,
                recall,
            )
        else:
            record.status = ModelStatus.DEPRECATED
            logger.warning(
                "ModelRegistry: v%s failed offline validation (P=%.3f R=%.3f) "
                "- thresholds P>=%.2f R>=%.2f",
                version,
                precision,
                recall,
                _MIN_PRECISION,
                _MIN_RECALL,
            )
        self._update_record(
            version,
            {
                "offline_precision": record.offline_precision,
                "offline_recall": record.offline_recall,
                "notes": record.notes,
                "status": record.status,
            },
        )
        return record

    def start_canary(
        self,
        version: str,
        cohort: str = "canary_cohort",
    ) -> ModelRecord:
        record = self._get(version)
        if record.status != ModelStatus.OFFLINE_VALIDATED:
            raise RuntimeError(
                f"ModelRegistry: cannot start canary from status={record.status!r}"
            )
        record.status = ModelStatus.CANARY
        record.canary_cohort = cohort
        self._update_record(version, {"status": record.status, "canary_cohort": cohort})
        logger.info("ModelRegistry: v%s started canary on cohort=%s", version, cohort)
        return record

    def record_canary_result(
        self,
        version: str,
        precision: float,
        recall: float,
    ) -> ModelRecord:
        record = self._get(version)
        record.canary_precision = round(precision, 4)
        record.canary_recall = round(recall, 4)
        self._update_record(
            version,
            {
                "canary_precision": record.canary_precision,
                "canary_recall": record.canary_recall,
            },
        )
        logger.info(
            "ModelRegistry: v%s canary result (P=%.3f R=%.3f)",
            version,
            precision,
            recall,
        )
        return record

    def promote(
        self,
        version: str,
        rollback_target_version: Optional[str] = None,
        force: bool = False,
    ) -> ModelRecord:
        record = self._get(version)
        if record.status != ModelStatus.CANARY:
            raise RuntimeError(
                f"ModelRegistry: cannot promote from status={record.status!r}"
            )

        if record.canary_precision is None or record.canary_recall is None:
            raise RuntimeError(
                "ModelRegistry: canary KPIs not recorded - "
                "call record_canary_result() first"
            )

        if not force and (
            record.canary_precision < _MIN_CANARY_PRECISION
            or record.canary_recall < _MIN_CANARY_RECALL
        ):
            raise RuntimeError(
                f"ModelRegistry: canary KPI thresholds not met "
                f"(P={record.canary_precision:.3f} R={record.canary_recall:.3f}) "
                f"- thresholds P>={_MIN_CANARY_PRECISION} R>={_MIN_CANARY_RECALL}"
            )

        if rollback_target_version:
            if not self.get(rollback_target_version):
                raise RuntimeError(
                    f"ModelRegistry: rollback_target_version={rollback_target_version!r} "
                    f"not registered"
                )
            record.rollback_target_version = rollback_target_version
        else:
            active = self._get_active_version()
            if active and active != version:
                record.rollback_target_version = active

        active_ver = self._get_active_version()
        if active_ver and active_ver != version:
            old = self.get(active_ver)
            if old and old.status == ModelStatus.PROMOTED:
                self._update_record(active_ver, {"status": ModelStatus.DEPRECATED})

        promoted_at = datetime.now(timezone.utc).isoformat()
        record.status = ModelStatus.PROMOTED
        record.promoted_at = promoted_at
        if force:
            record.notes = (
                f"{record.notes}\n[FORCED PROMOTION] Gate overridden: "
                f"P={record.canary_precision:.3f} R={record.canary_recall:.3f} "
                f"(thresholds P>={_MIN_CANARY_PRECISION} R>={_MIN_CANARY_RECALL})"
            ).strip()
            logger.warning(
                "ModelRegistry: v%s FORCE-PROMOTED - gate thresholds not met "
                "(P=%.3f R=%.3f, required P>=%.2f R>=%.2f)",
                version,
                record.canary_precision,
                record.canary_recall,
                _MIN_CANARY_PRECISION,
                _MIN_CANARY_RECALL,
            )

        self._update_record(
            version,
            {
                "status": record.status,
                "promoted_at": promoted_at,
                "rollback_target_version": record.rollback_target_version,
                "notes": record.notes,
            },
        )
        self._set_active_version(version)
        logger.info(
            "ModelRegistry: v%s PROMOTED to active (rollback_target=%s force=%s)",
            version,
            record.rollback_target_version,
            force,
        )
        self._signal_reload(version)
        return record

    def rollback(self) -> ModelRecord:
        active_ver = self._get_active_version()
        if not active_ver:
            raise RuntimeError("ModelRegistry: no active model to roll back from")
        active = self._get(active_ver)
        target_ver = active.rollback_target_version
        if not target_ver:
            raise RuntimeError(
                f"ModelRegistry: active v{active_ver} has no rollback target"
            )
        target = self._get(target_ver)
        self._update_record(active_ver, {"status": ModelStatus.ROLLBACK})
        self._update_record(target_ver, {"status": ModelStatus.PROMOTED})
        self._set_active_version(target_ver)
        logger.warning(
            "ModelRegistry: ROLLBACK - demoted v%s, restored v%s",
            active_ver,
            target_ver,
        )
        self._signal_reload(target_ver)
        return self._get(target_ver)

    def _signal_reload(self, version: str) -> None:
        import httpx

        endpoint = os.getenv("CODING_MODEL_ENDPOINT", "http://localhost:8004")
        timeout = float(os.getenv("MODEL_RELOAD_TIMEOUT_S", "120"))
        try:
            resp = httpx.post(
                f"{endpoint}/reload",
                json={"version": version},
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "ModelRegistry: inference service reloaded to v%s in %dms",
                data.get("active_version"),
                data.get("elapsed_ms", 0),
            )
        except Exception:
            logger.warning(
                "ModelRegistry: could not signal /reload on %s - "
                "inference service may still be on old version. "
                "Call POST /reload manually or restart the service.",
                endpoint,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_active(self) -> Optional[ModelRecord]:
        ver = self._get_active_version()
        if not ver:
            return None
        return self.get(ver)

    def get(self, version: str) -> Optional[ModelRecord]:
        from libs.cypher.model_registry_queries import GET_MODEL_VERSION

        rows = self._client.run(GET_MODEL_VERSION, version=version)
        if not rows:
            return None
        return _row_to_record(rows[0])

    def list_all(self) -> list[ModelRecord]:
        from libs.cypher.model_registry_queries import LIST_MODEL_VERSIONS

        rows = self._client.run(LIST_MODEL_VERSIONS)
        return [_row_to_record(r) for r in rows]
