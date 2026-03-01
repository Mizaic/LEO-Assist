"""ModelExtractorProvider: spaCy NER model extraction backend.

Supports two modes controlled by ``CODING_MODEL_PROVIDER``:

  ``service`` (default, recommended for production):
      Worker calls a remote inference service endpoint, so the model replicas
      can scale independently from the coding workers.

  ``inproc``:
      Model is loaded into the worker process.  Useful for local dev and as
      a resilience layer when the service is unavailable.

Environment variables
---------------------
CODING_MODEL_PROVIDER     "inproc" | "service"   (default: "service")
CODING_MODEL_ENDPOINT     http://host:port        (service mode only)
CODING_MODEL_TIMEOUT_MS   int milliseconds        (default: 10000)
CODING_MODEL_MAX_RETRIES  int                     (default: 2)
CODING_MODEL_PATH         path to spaCy model dir (inproc mode only)
CODING_MODEL_NAME         model display name
CODING_MODEL_VERSION      model version string
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from libs.ner.observable_post_processor import parse_measurement_from_text
from services.coding_worker.app.pipeline.extractor_contract import (
    CONTRACT_VERSION,
    ExtractionItem,
)

logger = logging.getLogger(__name__)

_SOURCE = "model"

_NER_TO_ASSERTION: dict[str, str] = {
    "NEG": "absent",
    "UNCERTAIN": "possible",
    "HIST": "historical",
    "FAM": "family",
}


class ModelExtractorProvider:
    """ExtractorProvider backed by a trained spaCy NER model."""

    source = _SOURCE

    def __init__(self) -> None:
        self._mode = os.getenv("CODING_MODEL_PROVIDER", "service")
        self._endpoint = os.getenv("CODING_MODEL_ENDPOINT", "http://localhost:8004")
        self._timeout = int(os.getenv("CODING_MODEL_TIMEOUT_MS", "10000")) / 1000.0
        self._max_retries = int(os.getenv("CODING_MODEL_MAX_RETRIES", "2"))
        self._model_name_cfg = os.getenv("CODING_MODEL_NAME", "medspacy_clinical_ner")
        self._model_version_cfg = os.getenv("CODING_MODEL_VERSION", "unknown")
        self._nlp: Any = None

    @property
    def model_name(self) -> str:
        return self._model_name_cfg

    @property
    def model_version(self) -> str:
        return self._model_version_cfg

    def is_available(self) -> bool:
        if self._mode == "inproc":
            return self._load_inproc() is not None
        try:
            resp = httpx.get(f"{self._endpoint}/health", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    def extract_batch(
        self,
        encounter_text: str,
        sentences: list,
    ) -> list[ExtractionItem]:
        if self._mode == "inproc":
            return self._extract_inproc(encounter_text, sentences)
        return self._extract_service(encounter_text, sentences)

    # ------------------------------------------------------------------
    # In-process mode
    # ------------------------------------------------------------------

    def _load_inproc(self) -> Any:
        if self._nlp is not None:
            return self._nlp
        model_path = os.getenv("CODING_MODEL_PATH", "")
        if not model_path:
            return None
        try:
            import spacy
            self._nlp = spacy.load(model_path)
            logger.info("ModelExtractorProvider: loaded in-process model from %s", model_path)
            return self._nlp
        except Exception:
            logger.warning(
                "ModelExtractorProvider: failed to load model from %s", model_path,
                exc_info=True,
            )
            return None

    def _extract_inproc(
        self, encounter_text: str, sentences: list
    ) -> list[ExtractionItem]:
        nlp = self._load_inproc()
        if nlp is None:
            raise RuntimeError("ModelExtractorProvider: no in-process model available")
        items: list[ExtractionItem] = []
        for sent in sentences:
            doc = nlp(sent.text)
            for ent in doc.ents:
                assertion = self._label_to_assertion(ent.label_)
                parsed = parse_measurement_from_text(ent.text) if ent.label_.lower() == "observable_entity" else {}
                items.append(ExtractionItem(
                    sentence_id=sent.sentence_id,
                    text=ent.text,
                    span_start=sent.start + ent.start_char,
                    span_end=sent.start + ent.end_char,
                    semantic_tag=ent.label_.lower(),
                    assertion=assertion,
                    confidence=round(float(getattr(ent, "kb_id_", 0.0) or 0.0), 4),
                    normalized=ent.text,
                    source_meta={"label": ent.label_},
                    relations=[],
                    numeric_value=str(parsed.get("numeric_value", "")).strip(),
                    unit=str(parsed.get("unit", "")).strip(),
                    reference_range=str(parsed.get("reference_range", "")).strip(),
                    source=_SOURCE,
                    model_name=self.model_name,
                    model_version=self.model_version,
                    contract_version=CONTRACT_VERSION,
                ))
        return items

    # ------------------------------------------------------------------
    # Service mode
    # ------------------------------------------------------------------

    def _extract_service(
        self, encounter_text: str, sentences: list
    ) -> list[ExtractionItem]:
        payload = {
            "text": encounter_text,
            "sentences": [
                {
                    "sentence_id": s.sentence_id,
                    "text": s.text,
                    "start": s.start,
                    "end": s.end,
                }
                for s in sentences
            ],
        }
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = httpx.post(
                    f"{self._endpoint}/extract",
                    json=payload,
                    timeout=self._timeout,
                )
                resp.raise_for_status()
                return self._parse_service_response(resp.json(), sentences)
            except Exception as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    logger.warning(
                        "ModelExtractorProvider: attempt %d/%d failed: %s",
                        attempt + 1,
                        self._max_retries + 1,
                        exc,
                    )
        raise RuntimeError(
            f"ModelExtractorProvider: all {self._max_retries + 1} attempts failed: {last_exc}"
        ) from last_exc

    def _parse_service_response(
        self,
        data: dict[str, Any],
        sentences: list,
    ) -> list[ExtractionItem]:
        sent_map = {s.sentence_id: s for s in sentences}
        items: list[ExtractionItem] = []
        for ent in data.get("entities", []):
            sid = ent.get("sentence_id", "")
            sent = sent_map.get(sid)
            assertion = self._label_to_assertion(ent.get("label", ""))
            semantic_tag = ent.get("semantic_tag", ent.get("label", "other")).lower()
            text = ent.get("text", "")
            parsed = parse_measurement_from_text(text) if semantic_tag == "observable_entity" else {}
            items.append(ExtractionItem(
                sentence_id=sid,
                text=text,
                span_start=ent.get("span_start", sent.start if sent else 0),
                span_end=ent.get("span_end", sent.end if sent else 0),
                semantic_tag=semantic_tag,
                assertion=assertion,
                confidence=float(ent.get("confidence", 0.0)),
                normalized=ent.get("normalized", text),
                source_meta=ent.get("source_meta", {}),
                relations=ent.get("relations", []),
                numeric_value=str(ent.get("value", ent.get("numeric_value", parsed.get("numeric_value", ""))) or "").strip(),
                unit=str(ent.get("unit", parsed.get("unit", "")) or "").strip(),
                reference_range=str(
                    ent.get(
                        "reference_range",
                        ent.get("referenceRange", parsed.get("reference_range", "")),
                    )
                    or ""
                ).strip(),
                source=_SOURCE,
                model_name=self.model_name,
                model_version=self.model_version,
                contract_version=CONTRACT_VERSION,
            ))
        return items

    @staticmethod
    def _label_to_assertion(label: str) -> str:
        upper = label.upper()
        for key, val in _NER_TO_ASSERTION.items():
            if key in upper:
                return val
        return "present"
