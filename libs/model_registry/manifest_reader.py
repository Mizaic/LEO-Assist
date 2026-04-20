"""Training manifest reader and cross-plan compatibility gate.

Atlas trace:
  DO: DO-0F42967F
  DI: DI-86A1E16F
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-0F42967F")

Reads the ``manifest.json`` produced by the NER training pipeline and verifies
that the model artifact references compatible schema/deid/label-mapping versions
before the model can be promoted to production.

Cross-plan contract (ner_training_set_refactor_bffc2bb3)
---------------------------------------------------------
The training plan owns dataset generation, de-identification, and manifest
production.  This plan (extractor_backend_cutover) owns the runtime gate.
Communication is via ``manifest.json`` only — no direct imports across plans.

Expected manifest.json schema
-----------------------------
{
  "schema_version":       "1.0",
  "deid_version":         "1.0",
  "label_mapping_version": "1.0",
  "dataset_version":      "20260101",
  "split": {"train": 0.8, "dev": 0.1, "test": 0.1},
  "entity_counts":        {"finding": 1200, "disease": 800, ...},
  "created_at":           "2026-01-01T00:00:00Z"
}
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Minimum accepted versions (semver-like strings; exact match required by default)
_REQUIRED_SCHEMA_VERSION = os.getenv("MODEL_REQUIRED_SCHEMA_VERSION", "1.0")
_REQUIRED_DEID_VERSION = os.getenv("MODEL_REQUIRED_DEID_VERSION", "1.0")
_REQUIRED_LABEL_VERSION = os.getenv("MODEL_REQUIRED_LABEL_VERSION", "1.0")


@dataclass
class ManifestSchema:
    """Parsed training manifest."""

    schema_version: str
    deid_version: str
    label_mapping_version: str
    dataset_version: str
    split: dict[str, float] = field(default_factory=dict)
    entity_counts: dict[str, int] = field(default_factory=dict)
    created_at: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ManifestSchema":
        return cls(
            schema_version=str(d.get("schema_version", "")),
            deid_version=str(d.get("deid_version", "")),
            label_mapping_version=str(d.get("label_mapping_version", "")),
            dataset_version=str(d.get("dataset_version", "")),
            split=d.get("split", {}),
            entity_counts=d.get("entity_counts", {}),
            created_at=d.get("created_at", ""),
            raw=d,
        )


@dataclass
class CompatibilityResult:
    """Result of the compatibility gate check."""

    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest: Optional[ManifestSchema] = None

    def raise_if_failed(self) -> None:
        if not self.passed:
            raise RuntimeError(
                "CompatibilityGate: model promotion blocked — "
                + "; ".join(self.failures)
            )


def read_manifest(manifest_path: str | Path) -> ManifestSchema:
    """Parse a training manifest.json file.

    Args:
        manifest_path: Path to the manifest file.

    Returns:
        Parsed ManifestSchema.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If required fields are missing.
    """
    p = Path(manifest_path)
    if not p.exists():
        raise FileNotFoundError(f"Manifest not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    m = ManifestSchema.from_dict(data)
    missing = [
        f
        for f in (
            "schema_version",
            "deid_version",
            "label_mapping_version",
            "dataset_version",
        )
        if not getattr(m, f)
    ]
    if missing:
        raise ValueError(f"Manifest missing required fields: {missing}")
    return m


class CompatibilityGate:
    """Checks that a model artifact is compatible with the runtime contract.

    Intended use — called before ``ModelRegistry.promote()``:

        gate = CompatibilityGate()
        result = gate.check(manifest_path, model_record)
        result.raise_if_failed()
        registry.promote(model_record.model_version)
    """

    def __init__(
        self,
        required_schema_version: str = _REQUIRED_SCHEMA_VERSION,
        required_deid_version: str = _REQUIRED_DEID_VERSION,
        required_label_version: str = _REQUIRED_LABEL_VERSION,
    ) -> None:
        self._schema = required_schema_version
        self._deid = required_deid_version
        self._label = required_label_version

    def check(
        self,
        manifest_path: str | Path,
        model_schema_version: str,
        model_deid_version: str,
        model_label_mapping_version: str,
        model_dataset_version: str,
    ) -> CompatibilityResult:
        """Run all compatibility checks.

        Args:
            manifest_path: Path to training plan manifest.json.
            model_schema_version: Schema version declared in the model artifact.
            model_deid_version: De-id version declared in the model artifact.
            model_label_mapping_version: Label mapping version in the model artifact.
            model_dataset_version: Dataset version in the model artifact.

        Returns:
            CompatibilityResult with ``passed`` flag and failure/warning messages.
        """
        result = CompatibilityResult(passed=True)

        # Read manifest
        try:
            manifest = read_manifest(manifest_path)
            result.manifest = manifest
        except Exception as exc:
            result.passed = False
            result.failures.append(f"manifest_read_error: {exc}")
            return result

        # Check versions match between manifest and model artifact metadata
        checks = [
            (
                "schema_version",
                manifest.schema_version,
                model_schema_version,
                self._schema,
            ),
            ("deid_version", manifest.deid_version, model_deid_version, self._deid),
            (
                "label_mapping_version",
                manifest.label_mapping_version,
                model_label_mapping_version,
                self._label,
            ),
        ]
        for name, manifest_val, model_val, required_val in checks:
            if manifest_val != model_val:
                result.failures.append(
                    f"{name}: manifest={manifest_val!r} does not match "
                    f"model artifact={model_val!r}"
                )
                result.passed = False
            if manifest_val != required_val:
                # Warn if manifest version is newer than required (forward compat)
                result.warnings.append(
                    f"{name}: manifest={manifest_val!r} differs from "
                    f"runtime required={required_val!r}"
                )

        # Dataset version consistency
        if manifest.dataset_version != model_dataset_version:
            result.failures.append(
                f"dataset_version: manifest={manifest.dataset_version!r} does not match "
                f"model artifact={model_dataset_version!r}"
            )
            result.passed = False

        if result.passed:
            logger.info(
                "CompatibilityGate: PASSED (schema=%s deid=%s labels=%s dataset=%s)",
                manifest.schema_version,
                manifest.deid_version,
                manifest.label_mapping_version,
                manifest.dataset_version,
            )
        else:
            logger.error(
                "CompatibilityGate: FAILED — %s",
                "; ".join(result.failures),
            )
        if result.warnings:
            logger.warning(
                "CompatibilityGate: warnings — %s",
                "; ".join(result.warnings),
            )

        return result
