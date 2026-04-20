"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-1D5031E0
  DI: DI-702F4583
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-1D5031E0")
"""
from __future__ import annotations

import logging
import os

import httpx

from libs.auth.service_auth import get_service_auth_header
from libs.ner.extractor_contract import ExtractionItem
from libs.ner.schema_mapper import LABEL_TO_SNOMED_TAG, normalise_label

logger = logging.getLogger(__name__)


class ModelExtractorProvider:
    source = "model"

    def __init__(self) -> None:
        self.model_name = "model-inference"
        self.model_version = "1.0"
        self._health_url = os.getenv(
            "MODEL_INFERENCE_HEALTH_URL",
            "http://localhost:8004/health",
        )
        self._extract_url = os.getenv(
            "MODEL_INFERENCE_EXTRACT_URL",
            "http://localhost:8004/extract",
        )
        self._reload_url = os.getenv(
            "MODEL_INFERENCE_RELOAD_URL",
            "http://localhost:8004/reload",
        )
        self._enabled = os.getenv("CODING_MODEL_PROVIDER_ENABLED", "true").lower() in {
            "true",
            "1",
            "yes",
            "on",
        }

    def is_available(self) -> bool:
        if not self._enabled:
            return False
        try:
            httpx.get(
                self._health_url, timeout=2.0, headers={**get_service_auth_header()}
            )
            return True
        except Exception:
            return False

    def _to_item(
        self, raw: dict, sentence_index: dict[str, str]
    ) -> ExtractionItem | None:
        sentence_id = str(raw.get("sentence_id") or "").strip()
        if not sentence_id:
            return None
        entity_text = str(raw.get("text") or "").strip()
        if not entity_text:
            return None

        canonical_label = normalise_label(
            str(raw.get("semantic_tag") or raw.get("label") or "")
        )
        if not canonical_label:
            return None
        semantic_tag = LABEL_TO_SNOMED_TAG.get(canonical_label, canonical_label)

        try:
            start = int(raw.get("span_start"))
            end = int(raw.get("span_end"))
            confidence = float(raw.get("confidence") or 0.0)
        except (TypeError, ValueError):
            return None

        normalized = str(raw.get("normalized") or entity_text).strip() or entity_text

        return ExtractionItem(
            sentence_id=sentence_index.get(sentence_id, sentence_id),
            text=entity_text,
            span_start=start,
            span_end=end,
            semantic_tag=semantic_tag,
            assertion="present",
            confidence=confidence,
            normalized=normalized,
            source_meta=dict(raw.get("source_meta") or {}),
            source=self.source,
            model_name=self.model_name,
            model_version=self.model_version,
        )

    @staticmethod
    def _build_fallback_extractor():
        from libs.pipeline_graph.subgraphs._extractor import build_extractor

        return build_extractor()

    def _ensure_model_version(
        self,
        requested_model_version: str | None,
        *,
        strict: bool = False,
    ) -> None:
        wanted = str(requested_model_version or "").strip()
        if not wanted:
            return
        hdrs = {**get_service_auth_header()}
        try:
            with httpx.Client(timeout=5.0) as client:
                health = client.get(self._health_url, headers=hdrs)
                health.raise_for_status()
                active = str((health.json() or {}).get("active_version") or "").strip()
                if active == wanted:
                    self.model_version = active
                    return
                reload_res = client.post(
                    self._reload_url,
                    json={"version": wanted},
                    headers=hdrs,
                )
                try:
                    reload_res.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    detail = (exc.response.text or "").strip()
                    suffix = f" detail={detail}" if detail else ""
                    raise RuntimeError(
                        f"Model reload failed for {wanted}: "
                        f"HTTP {exc.response.status_code}.{suffix}"
                    ) from exc
                verify = client.get(self._health_url, headers=hdrs)
                verify.raise_for_status()
                active_after = str(
                    (verify.json() or {}).get("active_version") or ""
                ).strip()
                self.model_version = active_after or wanted
                if strict and active_after != wanted:
                    raise RuntimeError(
                        f"Requested model version {wanted} but active is {active_after or 'unknown'}"
                    )
        except Exception as exc:
            if strict:
                raise
            logger.warning("Model version override failed (wanted=%s): %s", wanted, exc)

    @staticmethod
    def _enforce_requested_vs_actual_version(
        requested_model_version: str | None,
        actual_model_version: str | None,
        *,
        strict: bool,
    ) -> None:
        wanted = str(requested_model_version or "").strip()
        actual = str(actual_model_version or "").strip()
        if not wanted or not actual or wanted == actual:
            return
        message = (
            f"Requested model version {wanted} but extraction returned model version {actual}"
        )
        if strict:
            raise RuntimeError(message)
        logger.warning(message)

    def extract_batch(
        self,
        encounter_text: str,
        sentences: list,
        requested_model_version: str | None = None,
        strict_model_version: bool = False,
    ) -> list[ExtractionItem]:
        if not self._enabled:
            logger.warning(
                "Model extractor backend disabled; falling back to LLM extraction "
                "for this run"
            )
            fallback_extractor = self._build_fallback_extractor()
            return fallback_extractor.extract_batch(encounter_text, sentences)
        self._ensure_model_version(
            requested_model_version,
            strict=strict_model_version,
        )
        payload = {
            "text": encounter_text,
            "sentences": [
                {
                    "sentence_id": str(s.sentence_id),
                    "text": str(s.text),
                    "start": int(s.start),
                    "end": int(s.end),
                }
                for s in sentences
            ],
        }
        sentence_index = {str(s.sentence_id): str(s.sentence_id) for s in sentences}
        hdrs = {**get_service_auth_header()}
        with httpx.Client(timeout=15.0) as client:
            response = client.post(self._extract_url, json=payload, headers=hdrs)
            response.raise_for_status()
            data = response.json()

        self.model_name = str(data.get("model_name") or self.model_name)
        self.model_version = str(data.get("model_version") or self.model_version)
        self._enforce_requested_vs_actual_version(
            requested_model_version,
            self.model_version,
            strict=strict_model_version,
        )

        items: list[ExtractionItem] = []
        for raw in data.get("entities", []):
            if not isinstance(raw, dict):
                continue
            item = self._to_item(raw, sentence_index)
            if item is not None:
                items.append(item)
        return items
