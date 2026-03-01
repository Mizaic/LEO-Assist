"""Model lifecycle registry for spaCy NER models.

Provides:
- ModelRecord     — versioned model metadata
- ModelRegistry   — local registry with validation, canary, rollback
- CompatibilityGate — checks training manifest before promotion
- TrainingAdapter   — bridges training JSON to runtime ExtractionItem
"""

from libs.model_registry.registry import (
    ModelRecord,
    ModelRegistry,
    ModelStatus,
    get_registry,
)
from libs.model_registry.manifest_reader import (
    ManifestSchema,
    CompatibilityGate,
    CompatibilityResult,
    read_manifest,
)
from libs.model_registry.training_adapter import (
    TrainingAdapter,
    TrainingRecord,
)

__all__ = [
    "ModelRecord",
    "ModelRegistry",
    "ModelStatus",
    "get_registry",
    "ManifestSchema",
    "CompatibilityGate",
    "CompatibilityResult",
    "read_manifest",
    "TrainingAdapter",
    "TrainingRecord",
]
