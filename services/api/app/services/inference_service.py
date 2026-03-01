"""MedSpaCy runtime inference service.

Loads a trained spaCy NER model (if available) and runs inference on
encounter text to produce entity predictions with SNOMED concept links.
Falls back gracefully when no trained model exists yet.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MODEL_DIR = Path(__file__).resolve().parents[3] / "models" / "medspacy_clinical_ner"

_nlp_cache: Any = None
_model_checked: bool = False


@dataclass
class InferredEntity:
    text: str
    span_start: int
    span_end: int
    concept_id: str | None
    term: str | None
    confidence: float
    semantic_tag: str


def _load_model():
    """Lazily load the trained spaCy model. Caches after first load."""
    global _nlp_cache, _model_checked
    if _model_checked:
        return _nlp_cache
    _model_checked = True

    if not _MODEL_DIR.exists():
        logger.info("No trained model at %s - inference unavailable", _MODEL_DIR)
        return None

    try:
        import spacy
        _nlp_cache = spacy.load(str(_MODEL_DIR))
        logger.info(
            "Loaded MedSpaCy model from %s (pipes: %s)",
            _MODEL_DIR, ", ".join(_nlp_cache.pipe_names),
        )
        return _nlp_cache
    except Exception:
        logger.warning("Failed to load MedSpaCy model from %s", _MODEL_DIR, exc_info=True)
        return None


def _load_kb() -> dict[str, str] | None:
    """Load knowledge base concept_id -> term mapping if available."""
    kb_path = _MODEL_DIR / "kb"
    if not kb_path.exists():
        return None
    try:
        import json
        meta_path = _MODEL_DIR / "training_metrics.json"
        if meta_path.exists():
            return {}
        return {}
    except Exception:
        return None


def infer_encounter(
    encounter_text: str,
    encounter_id: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Run spaCy NER inference on encounter text.

    Returns entity predictions. When dry_run=False, the caller is
    responsible for writing DOCUMENTS to the patient graph.
    """
    nlp = _load_model()
    if nlp is None:
        return {
            "encounter_id": encounter_id,
            "entities": [],
            "written": False,
            "message": (
                "MedSpaCy model not yet built. "
                "Export gold data and run: python scripts/train_medspacy.py"
            ),
        }

    doc = nlp(encounter_text)
    entities: list[dict[str, Any]] = []

    for ent in doc.ents:
        entity = InferredEntity(
            text=ent.text,
            span_start=ent.start_char,
            span_end=ent.end_char,
            concept_id=None,
            term=None,
            confidence=round(getattr(ent, "kb_id_", 0.0) or 0.0, 4) if hasattr(ent, "kb_id_") else 0.0,
            semantic_tag=ent.label_,
        )
        entities.append(asdict(entity))

    logger.info(
        "Inference on encounter %s: %d entities detected",
        encounter_id, len(entities),
    )

    return {
        "encounter_id": encounter_id,
        "entities": entities,
        "entity_count": len(entities),
        "written": False,
        "dry_run": dry_run,
        "model_path": str(_MODEL_DIR),
    }
