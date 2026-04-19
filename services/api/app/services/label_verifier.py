"""Background dual-model verification for TrainingLabel entities.

Runs AWS + Azure small models over included labels in Neo4j. Agreements are
applied automatically; disagreements are pushed into LabelVerificationReview
for human resolution.

Concurrency model
-----------------
All LLM calls run in a shared ThreadPoolExecutor (max_workers configurable via
LABEL_VERIFY_WORKERS env var, default 20).  Each worker processes one label —
calling both AWS and Azure in a nested 2-thread pool — so with 20 outer workers
we have up to 40 concurrent LLM requests in flight at once.

Neo4j writes happen sequentially on the main thread as futures complete, so
we never need more than one Neo4j session open at a time.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
import threading
import time
from typing import Any

from libs.cypher.coding_review_queries import (
    GET_CODING_IGNORE_RULES,
    UPSERT_CODING_REVIEW,
)
from libs.cypher.label_verification_queries import (
    GET_HITL_REVIEWED_LABEL_IDS,
    RESOLVE_LABEL_VERIFICATION_REVIEW,
    UPDATE_LABEL_VERIFICATION,
    UPSERT_LABEL_VERIFICATION_REVIEW,
)
from libs.cypher.post_processor_rule_queries import GET_ACTIVE_POST_PROCESSOR_RULES
from libs.cypher.training_label_queries import (
    GET_ALL_INCLUDED_LABELS_FOR_EXPORT,
    UPDATE_TRAINING_LABEL_ENTITIES,
)
from libs.coding_engine.tier_classifier import classify_tier
from libs.llm_client.escalation import escalate_label
from libs.llm_client.factory import LLMResponse, create_llm
from libs.neo4j_client.client import PatientGraphClient
from libs.ner.post_processor_rules import (
    apply_rules_to_entities,
    parse_rules,
    PostProcessorRule,
)
from libs.ner.schema_mapper import LABEL_TO_SNOMED_TAG
from libs.prompts.registry import get_prompt, get_prompt_config
from libs.terminology.client import TerminologyClient

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

# Number of labels processed concurrently.
# Each worker runs AWS+Azure in parallel, so in-flight LLM requests are roughly 2x this value.
# For large backfills (e.g., 12k labels), tune LABEL_VERIFY_WORKERS via env for your infra limits.
_MAX_WORKERS = int(os.getenv("LABEL_VERIFY_WORKERS", "50"))
_AUTO_TRIAGE_TERM_THRESHOLD = float(os.getenv("AUTO_TRIAGE_TERM_THRESHOLD", "0.85"))
_AUTO_TRIAGE_LLM_THRESHOLD = float(os.getenv("AUTO_TRIAGE_LLM_THRESHOLD", "0.80"))
_LLM_RETRIES = int(os.getenv("LABEL_VERIFY_LLM_RETRIES", "4"))
_LLM_BACKOFF_BASE_S = float(os.getenv("LABEL_VERIFY_LLM_BACKOFF_BASE_S", "0.6"))
_CODING_MODE = os.getenv("CODING_MODE", "hitl").strip().lower()
_terminology_client: TerminologyClient | None = None

_AUTO_CODE_BLOCKED: frozenset[str] = frozenset(
    {
        "absent",
        "refuted",
        "declined",
        "cancelled",
        "planned",
        "hypothetical",
        "possible",
        "historical",
        "family",
    }
)

_ASSERTION_QUEUE_SET: frozenset[str] = frozenset(
    {
        "declined",
        "cancelled",
        "possible",
    }
)


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return max(minimum, default)


_ADAPTIVE_MIN_CONCURRENCY = _env_int(
    "LABEL_VERIFY_ADAPTIVE_MIN_CONCURRENCY", 20, minimum=1
)
_ADAPTIVE_MAX_CONCURRENCY = _env_int(
    "LABEL_VERIFY_ADAPTIVE_MAX_CONCURRENCY",
    max(_MAX_WORKERS * 2, _ADAPTIVE_MIN_CONCURRENCY),
    minimum=_ADAPTIVE_MIN_CONCURRENCY,
)
_ADAPTIVE_INITIAL_CONCURRENCY = _env_int(
    "LABEL_VERIFY_ADAPTIVE_INITIAL_CONCURRENCY",
    min(_ADAPTIVE_MAX_CONCURRENCY, _MAX_WORKERS * 2),
    minimum=_ADAPTIVE_MIN_CONCURRENCY,
)

VALID_ENTITY_LABELS = {
    "disorder",
    "finding",
    "procedure",
    "observable_entity",
    "qualifier_value",
    "substance",
    "medicinal_product",
    "clinical_drug",
    "situation",
    "event",
    "body_structure",
    "tumor_staging",
    "assessment_scale",
    "staging_scale",
    "regime_therapy",
    "record_artifact",
    "physical_object",
    "organism",
    "morphologic_abnormality",
    "occupation",
    "attribute",
    "environment",
    "product",
    "X_TEMPORAL",
    "X_DOSAGE",
    "X_FREQUENCY",
    "X_ROUTE",
}

_job_state_lock = threading.Lock()
_job_state: dict[str, Any] = {
    "status": "idle",
    "run_mode": "all",
    "reset_pending": False,
    "stop_requested": False,
    "started_at": None,
    "finished_at": None,
    "total": 0,
    "done": 0,
    "agreements": 0,
    "disagreements": 0,
    "auto_resolved": 0,
    "errors": 0,
    "pending_review": 0,
    "remaining": 0,
    "progress_pct": 0.0,
    "items_per_min": 0.0,
    "eta_seconds": None,
    "eta_at": None,
    "last_error": None,
}


class _AdaptiveLLMLimiter:
    """Throttle-aware concurrency gate for outbound LLM requests.

    - On repeated successes: slowly increase target concurrency.
    - On throttling/rate-limit signals: quickly reduce target concurrency.
    """

    def __init__(self, *, initial: int, minimum: int, maximum: int) -> None:
        self._min = minimum
        self._max = max(maximum, minimum)
        self._target = max(min(initial, self._max), self._min)
        self._in_flight = 0
        self._success_streak = 0
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)

    def acquire(self) -> None:
        with self._cv:
            while self._in_flight >= self._target:
                self._cv.wait(timeout=0.25)
            self._in_flight += 1

    def release(self) -> None:
        with self._cv:
            self._in_flight = max(0, self._in_flight - 1)
            self._cv.notify_all()

    def on_success(self) -> None:
        with self._cv:
            self._success_streak += 1
            # Conservative additive increase: +1 every 20 successful calls.
            if self._success_streak >= 20 and self._target < self._max:
                self._target += 1
                self._success_streak = 0
                self._cv.notify_all()

    def on_throttle(self) -> None:
        with self._cv:
            self._success_streak = 0
            # Multiplicative decrease: drop by ~30%, keep at least min.
            lowered = int(self._target * 0.7)
            self._target = max(self._min, lowered)
            self._cv.notify_all()

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "target": self._target,
                "in_flight": self._in_flight,
                "min": self._min,
                "max": self._max,
            }


_llm_limiter = _AdaptiveLLMLimiter(
    initial=_ADAPTIVE_INITIAL_CONCURRENCY,
    minimum=_ADAPTIVE_MIN_CONCURRENCY,
    maximum=_ADAPTIVE_MAX_CONCURRENCY,
)


def get_job_state() -> dict[str, Any]:
    with _job_state_lock:
        state = dict(_job_state)
    state["llm_concurrency"] = _llm_limiter.snapshot()
    return state


def _recompute_progress_locked() -> None:
    total = int(_job_state.get("total") or 0)
    done = int(_job_state.get("done") or 0)
    started_at = _job_state.get("started_at")
    now = time.time()

    remaining = max(0, total - done)
    _job_state["remaining"] = remaining
    _job_state["progress_pct"] = round((done / total) * 100.0, 2) if total else 0.0

    if not started_at or done <= 0:
        _job_state["items_per_min"] = 0.0
        _job_state["eta_seconds"] = None
        _job_state["eta_at"] = None
        return

    elapsed_s = max(1e-6, now - float(started_at))
    items_per_s = done / elapsed_s
    items_per_min = items_per_s * 60.0
    _job_state["items_per_min"] = round(items_per_min, 2)

    if items_per_s > 0 and remaining > 0:
        eta_seconds = int(round(remaining / items_per_s))
        _job_state["eta_seconds"] = eta_seconds
        _job_state["eta_at"] = now + eta_seconds
    else:
        _job_state["eta_seconds"] = 0 if remaining == 0 else None
        _job_state["eta_at"] = now if remaining == 0 else None


def begin_job() -> bool:
    """Attempt to mark the verifier job as running. Returns False if busy."""
    with _job_state_lock:
        if _job_state["status"] in {"running", "stopping"}:
            return False
        _job_state.update(
            {
                "status": "running",
                "run_mode": "all",
                "reset_pending": False,
                "stop_requested": False,
                "started_at": time.time(),
                "finished_at": None,
                "total": 0,
                "done": 0,
                "agreements": 0,
                "disagreements": 0,
                "auto_resolved": 0,
                "errors": 0,
                "pending_review": 0,
                "remaining": 0,
                "progress_pct": 0.0,
                "items_per_min": 0.0,
                "eta_seconds": None,
                "eta_at": None,
                "last_error": None,
            }
        )
    return True


def begin_job_with_mode(*, run_mode: str = "all", reset_pending: bool = False) -> bool:
    """Attempt to start verifier with explicit run mode.

    Supported run_modes:
      - "all": verify all included labels (re-verifies already-verified ones)
      - "hitl_only": re-verify only labels that had HITL-resolved reviews
      - "resume": continue from checkpoint — skip labels already verified
      - "re_extract": re-extract entities via LLM before running verification
    """
    mode = (
        run_mode if run_mode in {"all", "hitl_only", "resume", "re_extract"} else "all"
    )
    with _job_state_lock:
        if _job_state["status"] in {"running", "stopping"}:
            return False
        _job_state.update(
            {
                "status": "running",
                "run_mode": mode,
                "reset_pending": bool(reset_pending),
                "stop_requested": False,
                "started_at": time.time(),
                "finished_at": None,
                "total": 0,
                "done": 0,
                "agreements": 0,
                "disagreements": 0,
                "auto_resolved": 0,
                "errors": 0,
                "pending_review": 0,
                "remaining": 0,
                "progress_pct": 0.0,
                "items_per_min": 0.0,
                "eta_seconds": None,
                "eta_at": None,
                "last_error": None,
            }
        )
    return True


def request_stop_job() -> bool:
    """Request graceful cancellation of running verification."""
    with _job_state_lock:
        if _job_state.get("status") not in {"running", "stopping"}:
            return False
        _job_state["stop_requested"] = True
        _job_state["status"] = "stopping"
    return True


def _stop_requested() -> bool:
    with _job_state_lock:
        return bool(_job_state.get("stop_requested"))


def _patch_state(**updates: Any) -> None:
    with _job_state_lock:
        _job_state.update(updates)
        _recompute_progress_locked()


def _increment_state(**deltas: int) -> None:
    """Atomically increment numeric counters."""
    with _job_state_lock:
        for k, v in deltas.items():
            _job_state[k] = _job_state.get(k, 0) + v
        _recompute_progress_locked()


def _parse_model_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    m = _JSON_OBJECT_RE.search(text)
    if not m:
        return {}
    try:
        parsed = json.loads(m.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _normalise_label(label: str, fallback: str) -> str:
    label = (label or "").strip()
    if label in VALID_ENTITY_LABELS:
        return label
    tag_mapped = _snomed_tag_to_label(label)
    return tag_mapped if tag_mapped in VALID_ENTITY_LABELS else fallback


def _call_model_for_label(
    provider: str,
    text: str,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    client = create_llm(provider=provider, tier="small")
    system_prompt = get_prompt("label_verification", version=2)
    user_payload = {
        "text": text,
        "entities": [
            {"entity_index": i, "text": e.get("text", ""), "label": e.get("label", "")}
            for i, e in enumerate(entities)
        ],
    }
    for attempt in range(_LLM_RETRIES + 1):
        if _stop_requested():
            return []
        _llm_limiter.acquire()
        try:
            response: LLMResponse = client.converse(
                system=system_prompt,
                messages=[{"role": "user", "content": json.dumps(user_payload)}],
                max_tokens=1024,
                temperature=0.0,
                agent_task="label_verifier",
            )
            parsed = _parse_model_json(response.text)
            entity_rows = parsed.get("entities", [])
            _llm_limiter.on_success()
            return entity_rows if isinstance(entity_rows, list) else []
        except Exception as exc:
            msg = str(exc).lower()
            throttled = any(
                marker in msg
                for marker in (
                    "429",
                    "rate limit",
                    "ratelimit",
                    "throttle",
                    "too many requests",
                )
            )
            if throttled:
                _llm_limiter.on_throttle()
            if attempt >= _LLM_RETRIES:
                logger.warning(
                    "Label verification model call failed provider=%s",
                    provider,
                    exc_info=True,
                )
                return []
            delay = _LLM_BACKOFF_BASE_S * (2**attempt)
            if throttled:
                delay *= 1.5
            time.sleep(delay)
        finally:
            _llm_limiter.release()
    return []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        val = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, val))


def _snomed_tag_to_label(tag: str | None) -> str | None:
    if not tag:
        return None
    key = tag.strip().lower()
    mapping = {
        "qualifier value": "qualifier_value",
        "observable entity": "observable_entity",
        "body structure": "body_structure",
        "tumor staging": "tumor_staging",
        "assessment scale": "assessment_scale",
        "staging scale": "staging_scale",
        "regime/therapy": "regime_therapy",
        "record artifact": "record_artifact",
        "physical object": "physical_object",
        "morphologic abnormality": "morphologic_abnormality",
        "clinical drug": "clinical_drug",
        "medicinal product": "medicinal_product",
        "qualifier": "qualifier_value",
    }
    candidate = mapping.get(key, key.replace(" ", "_"))
    return candidate if candidate in VALID_ENTITY_LABELS else None


def _resolve_start(text: str, span_text: str, around: int = 0) -> int | None:
    if not span_text:
        return None
    positions: list[int] = []
    pos = text.find(span_text)
    while pos != -1:
        positions.append(pos)
        pos = text.find(span_text, pos + 1)
    if positions:
        return min(positions, key=lambda p: abs(p - around))
    hay = text.lower()
    needle = span_text.lower()
    positions = []
    pos = hay.find(needle)
    while pos != -1:
        positions.append(pos)
        pos = hay.find(needle, pos + 1)
    if positions:
        return min(positions, key=lambda p: abs(p - around))
    return None


# Entity-type normalisation and value-unit linking have been moved to the
# shared post-processing module: libs/pipeline/post_processing.py
try:
    from libs.pipeline.post_processing import (  # noqa: E402
        run_post_processing,
        _BARE_NUMERIC_RE,
        _EPISODE_MARKER_TEXTS,
        _MDT_OUTCOME_RE,
        _SEVERITY_MODIFIER_TEXTS,
        _SMOKING_CONSUMPTION_RE,
        _UNCERTAINTY_MARKER_RE,
        _has_nearby_observable,
        _is_bare_analyte,
        _is_lab_value_text,
        _is_lifestyle_topic_list,
        _is_numeric_measurement_text,
        _is_result_descriptor,
        _is_smoking_status_text,
    )
except Exception:  # pragma: no cover - fallback for lightweight test env
    import re
    import warnings

    warnings.warn(
        "libs.pipeline.post_processing import failed -- all 9 post-processing "
        "layers are DISABLED. This is acceptable in isolated test environments "
        "but MUST NOT happen in production.",
        RuntimeWarning,
        stacklevel=1,
    )
    logging.getLogger(__name__).error(
        "SAFETY: post-processing import failed -- lab-value guard, scope guard, "
        "context detection, and disorder gate are all disabled",
        exc_info=True,
    )

    def run_post_processing(*args, **kwargs):  # type: ignore[no-redef]
        return args[0] if args else []

    _BARE_NUMERIC_RE = re.compile(r"^\s*[+-]?\d+(?:\.\d+)?\s*$")
    _EPISODE_MARKER_TEXTS = set()
    _MDT_OUTCOME_RE = re.compile(r"$^")
    _SEVERITY_MODIFIER_TEXTS = set()
    _SMOKING_CONSUMPTION_RE = re.compile(r"$^")
    _UNCERTAINTY_MARKER_RE = re.compile(r"$^")

    def _has_nearby_observable(*args, **kwargs):  # type: ignore[no-redef]
        return False

    def _is_bare_analyte(*args, **kwargs):  # type: ignore[no-redef]
        return False

    def _is_lab_value_text(*args, **kwargs):  # type: ignore[no-redef]
        return False

    def _is_lifestyle_topic_list(*args, **kwargs):  # type: ignore[no-redef]
        return False

    def _is_numeric_measurement_text(*args, **kwargs):  # type: ignore[no-redef]
        return False

    def _is_result_descriptor(*args, **kwargs):  # type: ignore[no-redef]
        return False

    def _is_smoking_status_text(*args, **kwargs):  # type: ignore[no-redef]
        return False


_CLINICAL_LABELS = frozenset(
    {
        "disorder",
        "finding",
        "procedure",
        "observable_entity",
        "qualifier_value",
        "substance",
        "medicinal_product",
        "clinical_drug",
        "situation",
        "event",
        "body_structure",
        "tumor_staging",
        "assessment_scale",
        "staging_scale",
        "regime_therapy",
        "record_artifact",
        "morphologic_abnormality",
        "occupation",
        "attribute",
        "environment",
        "product",
    }
)


def _deterministic_resolve(
    entity_text: str,
    candidates: set[str],
    all_entities: list[dict[str, Any]],
    entity_idx: int,
    *,
    model_a_label: str = "",
    model_b_label: str = "",
) -> dict[str, Any] | None:
    """Check if deterministic rules produce a clear answer for a disagreement.

    Returns a triage-style dict if resolved, None otherwise.
    """
    text = entity_text.strip()
    lowered = text.lower()

    # X_NEGATION_CUE misuse: one model says X_NEGATION_CUE on a real clinical entity
    # while the other gives a valid clinical label. Trust the clinical label —
    # but only if the entity text isn't actually a negation word.
    _real_negation_words = {
        "no",
        "not",
        "denies",
        "denied",
        "nil",
        "without",
        "never",
        "none",
        "neither",
        "nor",
    }
    is_real_negation = lowered in _real_negation_words
    if not is_real_negation:
        if model_a_label == "X_NEGATION_CUE" and model_b_label in _CLINICAL_LABELS:
            return {
                "resolved_label": model_b_label,
                "confidence": 0.95,
                "method": "deterministic_rule",
                "reason": "X_NEGATION_CUE misuse — prefer clinical label",
            }
        if model_b_label == "X_NEGATION_CUE" and model_a_label in _CLINICAL_LABELS:
            return {
                "resolved_label": model_a_label,
                "confidence": 0.95,
                "method": "deterministic_rule",
                "reason": "X_NEGATION_CUE misuse — prefer clinical label",
            }

    # Numeric measurement labeled observable_entity by one model → qualifier_value.
    if "qualifier_value" in candidates:
        if _is_numeric_measurement_text(text):
            return {
                "resolved_label": "qualifier_value",
                "confidence": 0.99,
                "method": "deterministic_rule",
                "reason": "numeric measurement value",
            }
        if _BARE_NUMERIC_RE.match(text):
            return {
                "resolved_label": "qualifier_value",
                "confidence": 0.99,
                "method": "deterministic_rule",
                "reason": "bare numeric value",
            }
        if _is_lab_value_text(text):
            return {
                "resolved_label": "qualifier_value",
                "confidence": 0.99,
                "method": "deterministic_rule",
                "reason": "lab result value",
            }
        if _is_result_descriptor(text):
            return {
                "resolved_label": "qualifier_value",
                "confidence": 0.99,
                "method": "deterministic_rule",
                "reason": "result descriptor",
            }
        if lowered in _EPISODE_MARKER_TEXTS:
            return {
                "resolved_label": "qualifier_value",
                "confidence": 0.99,
                "method": "deterministic_rule",
                "reason": "episode marker",
            }
        if lowered in _SEVERITY_MODIFIER_TEXTS:
            return {
                "resolved_label": "qualifier_value",
                "confidence": 0.99,
                "method": "deterministic_rule",
                "reason": "severity modifier",
            }
        if _UNCERTAINTY_MARKER_RE.match(text):
            return {
                "resolved_label": "qualifier_value",
                "confidence": 0.99,
                "method": "deterministic_rule",
                "reason": "uncertainty marker",
            }

    # Smoking / lifestyle attribute → finding.
    if "finding" in candidates:
        if _is_smoking_status_text(text):
            return {
                "resolved_label": "finding",
                "confidence": 0.99,
                "method": "deterministic_rule",
                "reason": "smoking status",
            }
        if _is_lifestyle_topic_list(text):
            return {
                "resolved_label": "finding",
                "confidence": 0.99,
                "method": "deterministic_rule",
                "reason": "lifestyle factor",
            }

    # Bare analyte near observable → suppress (return special marker).
    if _is_bare_analyte(text) and _has_nearby_observable(all_entities, entity_idx):
        return {
            "resolved_label": "__suppress__",
            "confidence": 0.99,
            "method": "deterministic_rule",
            "reason": "bare analyte near observable",
        }

    # Smoking consumption frequency → qualifier_value.
    if "qualifier_value" in candidates and _SMOKING_CONSUMPTION_RE.search(text):
        return {
            "resolved_label": "qualifier_value",
            "confidence": 0.99,
            "method": "deterministic_rule",
            "reason": "smoking consumption frequency",
        }

    # MDT → procedure.
    if "procedure" in candidates and lowered == "mdt":
        return {
            "resolved_label": "procedure",
            "confidence": 0.99,
            "method": "deterministic_rule",
            "reason": "MDT is procedure",
        }

    # MDT outcome heading → record_artifact.
    if _MDT_OUTCOME_RE.search(text):
        return {
            "resolved_label": "record_artifact",
            "confidence": 0.99,
            "method": "deterministic_rule",
            "reason": "MDT outcome heading",
        }

    return None


def _auto_triage_disagreement(
    *,
    encounter_text: str,
    entity_text: str,
    current_label: str,
    model_a_label: str,
    model_b_label: str,
    model_a_rationale: str,
    model_b_rationale: str,
) -> dict[str, Any] | None:
    """Try to auto-resolve a disagreement via terminology API then LLM tie-break."""
    target_labels = {model_a_label, model_b_label}

    # 1) Terminology resolution path (with expected_tags for better ranking).
    snomed_tag = LABEL_TO_SNOMED_TAG.get(current_label)
    expected = {entity_text: snomed_tag} if snomed_tag else None
    results = _resolve_terms_via_api([entity_text], expected_tags=expected)
    candidates = results.get(entity_text) or []
    if candidates and isinstance(candidates, list):
        top = candidates[0] if isinstance(candidates[0], dict) else {}
        top_score = _safe_float(top.get("score"))
        top_tag = str(top.get("semantic_tag") or "")
        top_label = _snomed_tag_to_label(top_tag)
        logger.debug(
            "Auto-triage term lookup: entity=%r score=%.2f tag=%r mapped=%r targets=%r",
            entity_text,
            top_score,
            top_tag,
            top_label,
            target_labels,
        )
        if top_score >= _AUTO_TRIAGE_TERM_THRESHOLD and top_label in target_labels:
            return {
                "resolved_label": top_label,
                "confidence": top_score,
                "method": "terminology_api",
                "reason": f"top semantic tag {top_tag!r} score={top_score:.2f}",
            }

    # 2) Model escalation path (small -> big -> max).
    esc = escalate_label(
        entity_text=entity_text,
        encounter_text=encounter_text,
        current_label=current_label,
        model_a_label=model_a_label,
        model_b_label=model_b_label,
        model_a_rationale=model_a_rationale,
        model_b_rationale=model_b_rationale,
        allowed_labels=sorted(VALID_ENTITY_LABELS),
        system_prompt=get_prompt("label_disambiguation", version=1),
        confidence_threshold=_AUTO_TRIAGE_LLM_THRESHOLD,
        start_tier="small",
    )
    if esc.resolved and esc.label:
        resolved_label = _normalise_label(esc.label, current_label)
        if resolved_label in target_labels:
            return {
                "resolved_label": resolved_label,
                "confidence": esc.confidence,
                "method": f"escalation:{esc.model_tier}",
                "reason": esc.rationale,
                "model_tier": esc.model_tier,
                "model_id": esc.model_id,
            }
    return None


_CODEABLE_LABELS = frozenset(
    {
        "disorder",
        "finding",
        "procedure",
        "observable_entity",
        "substance",
        "medicinal_product",
        "clinical_drug",
        "situation",
        "body_structure",
        "morphologic_abnormality",
        "regime_therapy",
        "assessment_scale",
        "tumor_staging",
        "organism",
        "occupation",
        "physical_object",
    }
)

_CODING_SCORE_THRESHOLD = float(os.getenv("CODING_REVIEW_SCORE_THRESHOLD", "0.70"))
_CODING_ALT_LOW = float(os.getenv("CODING_ALT_THRESHOLD_LOW", "0.3"))
_CODING_ALT_ENABLED = os.getenv("CODING_ALT_ENABLED", "true").lower() == "true"

# Semantic tag cross-validation thresholds.
_TAG_XVAL_AUTO_RECLASSIFY_SCORE = float(
    os.getenv("TAG_XVAL_AUTO_RECLASSIFY_SCORE", "0.90")
)
_TAG_XVAL_SAME_TAG_CEILING = float(os.getenv("TAG_XVAL_SAME_TAG_CEILING", "0.50"))
_TAG_XVAL_MIN_DELTA = float(os.getenv("TAG_XVAL_MIN_DELTA", "0.10"))


def _cross_check_semantic_tag(
    entity_label: str,
    candidates: list[dict],
) -> tuple[str | None, float | None]:
    """Compare top SNOMED candidates' semantic tags against the entity label.

    Returns (suggested_label, score_delta) when the best unbiased candidate's
    semantic tag disagrees with the extraction label.  Returns (None, None)
    when tags agree or there are insufficient candidates to compare.
    """
    if not candidates:
        return None, None

    top_n = candidates[:3]

    best_same_score = 0.0
    best_diff_label: str | None = None
    best_diff_score = 0.0

    for c in top_n:
        tag = str(c.get("semantic_tag") or "")
        mapped = _snomed_tag_to_label(tag)
        if not mapped:
            continue
        score = _safe_float(c.get("score")) or 0.0

        if mapped == entity_label:
            best_same_score = max(best_same_score, score)
        elif score > best_diff_score:
            best_diff_score = score
            best_diff_label = mapped

    if not best_diff_label:
        return None, None

    delta = best_diff_score - best_same_score
    if delta < _TAG_XVAL_MIN_DELTA:
        return None, None

    return best_diff_label, delta


def _resolve_terms_via_api(
    terms: list[str],
    expected_tags: dict[str, str] | None = None,
) -> dict[str, list]:
    """Resolve a batch of terms via shared terminology client."""
    if not terms:
        return {}

    global _terminology_client
    if _terminology_client is None:
        _terminology_client = TerminologyClient(timeout=10, max_retries=1)

    try:
        raw_results = _terminology_client.resolve_raw(
            terms=terms,
            expected_tags=expected_tags,
        )
        normalised: dict[str, list[dict[str, Any]]] = {}
        for term, candidates in raw_results.items():
            term_candidates: list[dict[str, Any]] = []
            for candidate in candidates or []:
                if not isinstance(candidate, dict):
                    continue
                term_candidates.append(
                    {
                        "snomed_concept_id": (
                            candidate.get("snomed_concept_id")
                            or candidate.get("concept_id")
                            or candidate.get("conceptId")
                            or ""
                        ),
                        "snomed_term": (
                            candidate.get("snomed_term")
                            or candidate.get("term")
                            or candidate.get("preferredTerm")
                            or ""
                        ),
                        "semantic_tag": (
                            candidate.get("semantic_tag")
                            or candidate.get("semanticTag")
                            or ""
                        ),
                        "score": _safe_float(candidate.get("score")),
                    }
                )
            normalised[str(term)] = term_candidates
        return normalised
    except Exception:
        logger.debug("Coding check: terminology API call failed", exc_info=True)
        return {}


def _suggest_alt_terms(term: str, entity_label: str) -> list[str]:
    """Ask a small LLM for SNOMED-friendly alternative phrasings of a near-miss term.

    The prompt explicitly allows an empty response so the LLM does not hallucinate
    alternatives when none exist.
    """
    system_prompt = (
        "You are a UK primary care clinical terminology assistant. "
        "Your job is to suggest alternative phrasings that would match SNOMED CT concepts. "
        "If the term is too vague, ambiguous, or product-specific to have useful SNOMED "
        "alternatives, you MUST return an empty array []. "
        "Respond ONLY with a valid JSON array of strings -- no explanation, no markdown."
    )
    user_prompt = (
        f'Term: "{term}" (type: {entity_label})\n'
        "Suggest up to 3 alternatives: the preferred SNOMED term, a common abbreviation, "
        "and one synonym a UK GP might write. "
        "If you cannot suggest meaningful alternatives, return []. "
        'Output format: ["phrase1", "phrase2"] or []'
    )
    try:
        llm = create_llm(tier="small")
        response = llm.converse(
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=256,
            temperature=0.2,
            agent_task="label_verifier_alt_terms",
        )
        raw_text = response.text.strip()
        match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if not match:
            logger.debug(
                "Alt-term LLM: no JSON array for %r -- response: %s",
                term,
                raw_text[:120],
            )
            return []
        raw = json.loads(match.group())
        seen_lower = term.strip().lower()
        alts = [
            s.strip()
            for s in raw
            if isinstance(s, str) and s.strip() and s.strip().lower() != seen_lower
        ][:4]
        logger.debug("Alt-term LLM: %r -> %r", term, alts)
        return alts
    except Exception:
        logger.debug("Alt-term LLM call failed for %r", term, exc_info=True)
        return []


def _try_alt_coding(term: str, entity_label: str) -> dict | None:
    """Try LLM-suggested alternatives for a low-confidence term.

    Returns the best candidate dict if any alternative scores >= threshold, else None.
    Logs all alternatives and scores so decisions are auditable.
    """
    alt_terms = _suggest_alt_terms(term, entity_label)
    if not alt_terms:
        logger.info(
            "LLM-alt (verify): no alternatives suggested for %r (%s)",
            term,
            entity_label,
        )
        return None
    results = _resolve_terms_via_api(alt_terms)
    best: dict | None = None
    best_score = 0.0
    for alt in alt_terms:
        candidates = results.get(alt) or []
        top = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        score = _safe_float(top.get("score"))
        logger.info(
            "LLM-alt (verify): original=%r alt=%r -> concept=%r score=%s",
            term,
            alt,
            top.get("snomed_concept_id", ""),
            score,
        )
        if score >= _CODING_SCORE_THRESHOLD and score > best_score:
            best_score = score
            best = top
    if best:
        logger.info(
            "LLM-alt (verify): RESOLVED %r -> %r (%.4f)",
            term,
            best.get("snomed_term"),
            best_score,
        )
    else:
        logger.info("LLM-alt (verify): no alternative cleared threshold for %r", term)
    return best


def _build_review_item(
    label_id: str,
    idx: int,
    entity_text: str,
    entity_label: str,
    coded: bool,
    top: dict,
    score: float | None,
    assertion: str = "present",
    *,
    decision_tier: int | None = None,
    tier_reason: str | None = None,
    tier_decision: str | None = None,
    suggested_label: str | None = None,
    tag_mismatch_delta: float | None = None,
) -> dict[str, Any]:
    """Assemble a coding review dict for the queue."""
    concept_id = str(top.get("snomed_concept_id") or "")
    item: dict[str, Any] = {
        "review_id": f"coding:{label_id}:{idx}",
        "label_id": label_id,
        "entity_index": idx,
        "entity_text": entity_text,
        "entity_label": entity_label,
        "coded": coded,
        "snomed_concept_id": concept_id if coded else None,
        "snomed_term": str(top.get("snomed_term") or "") if coded else None,
        "score": score if coded else None,
        "semantic_tag": str(top.get("semantic_tag") or "") if coded else None,
        "assertion": assertion,
        "decision_tier": decision_tier,
        "tier_reason": tier_reason,
        "tier_decision": tier_decision,
    }
    if suggested_label:
        item["suggested_label"] = suggested_label
    if tag_mismatch_delta is not None:
        item["tag_mismatch_delta"] = round(tag_mismatch_delta, 4)
    return item


def _check_terminology_coding(
    label_id: str,
    entities: list[dict[str, Any]],
    ignore_texts: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Check each codeable entity against the terminology API.

    Returns coding review items for entities that are uncoded or low-confidence.
    Entities matching a coding ignore rule are suppressed before queuing.
    Near-miss entities (score >= _CODING_ALT_LOW) are tried against LLM
    alternatives before being added to the queue.

    The resolve call is deliberately **unbiased** (no expected_tags) so the
    returned candidates are ranked purely by lexical + vector similarity.
    This allows semantic-tag cross-validation: if the top candidate's SNOMED
    tag disagrees with the extracted entity label, the mismatch is flagged.
    """
    codeable = [
        (i, e)
        for i, e in enumerate(entities)
        if str(e.get("label", "")) in _CODEABLE_LABELS
        and str(e.get("assertion", "present")).strip().lower() not in _AUTO_CODE_BLOCKED
        and str(e.get("text", "")).strip()
    ]
    if not codeable:
        return []

    terms = list({str(e.get("text", "")).strip() for _, e in codeable})
    results_map = _resolve_terms_via_api(terms)
    reviews: list[dict[str, Any]] = []

    for idx, ent in codeable:
        entity_text = str(ent.get("text", "")).strip()
        entity_label = str(ent.get("label", ""))
        normalized = re.sub(r"\s+", " ", entity_text.lower())

        if normalized in ignore_texts:
            continue

        candidates = results_map.get(entity_text) or []
        top = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        concept_id = str(top.get("snomed_concept_id") or "")
        score = _safe_float(top.get("score"))
        coded = bool(concept_id)

        suggested_label, tag_delta = _cross_check_semantic_tag(entity_label, candidates)

        if suggested_label:
            if (
                tag_delta is not None
                and tag_delta
                >= (_TAG_XVAL_AUTO_RECLASSIFY_SCORE - _TAG_XVAL_SAME_TAG_CEILING)
                and score is not None
                and score >= _TAG_XVAL_AUTO_RECLASSIFY_SCORE
            ):
                logger.info(
                    "Tag cross-validation: auto-reclassifying %r from %s -> %s (delta=%.2f, score=%.2f)",
                    entity_text,
                    entity_label,
                    suggested_label,
                    tag_delta,
                    score,
                )
                ent["label"] = suggested_label
                entity_label = suggested_label
                suggested_label = None
                tag_delta = None
            else:
                logger.info(
                    "Tag cross-validation: mismatch for %r — extracted=%s, suggested=%s (delta=%.2f)",
                    entity_text,
                    entity_label,
                    suggested_label,
                    tag_delta or 0.0,
                )

        if coded and score >= _CODING_SCORE_THRESHOLD and not suggested_label:
            continue

        if (
            _CODING_ALT_ENABLED
            and coded
            and score is not None
            and score >= _CODING_ALT_LOW
            and not suggested_label
        ):
            alt = _try_alt_coding(entity_text, entity_label)
            if alt:
                continue

        assertion = str(ent.get("assertion") or "present")
        surface_form_status = str(ent.get("surface_form_status") or "")

        if suggested_label:
            tier_val = 2
            tier_reason_val = f"semantic_tag_mismatch: extracted={entity_label}, suggested={suggested_label}"
            tier_decision_val = "review"
        else:
            tier = classify_tier(
                assertion=assertion,
                context_failed=bool(ent.get("context_failed")),
                terminology_score=score or 0.0,
                surface_form_status=surface_form_status,
                coding_mode=_CODING_MODE,
            )
            tier_val = tier.tier
            tier_reason_val = tier.reason
            tier_decision_val = tier.decision

        reviews.append(
            _build_review_item(
                label_id,
                idx,
                entity_text,
                entity_label,
                coded,
                top,
                score,
                assertion,
                decision_tier=tier_val,
                tier_reason=tier_reason_val,
                tier_decision=tier_decision_val,
                suggested_label=suggested_label,
                tag_mismatch_delta=tag_delta,
            )
        )

    return reviews


# ---------------------------------------------------------------------------
# Per-label processing (runs inside the outer ThreadPoolExecutor)
# ---------------------------------------------------------------------------


class _LabelResult:
    """Carries everything needed to write one label's outcome to Neo4j."""

    __slots__ = (
        "label_id",
        "updated_entities",
        "quality_score",
        "agreement",
        "n_disagreements",
        "review_items",
        "first_aws_label",
        "first_azure_label",
        "auto_resolved",
        "auto_resolve_method",
        "coding_reviews",
        "error",
    )

    def __init__(self, label_id: str, *, error: bool = False):
        self.label_id = label_id
        self.updated_entities: list[dict] = []
        self.quality_score: float = 0.0
        self.agreement: bool = False
        self.n_disagreements: int = 0
        self.review_items: list[dict] = []
        self.first_aws_label: str = ""
        self.first_azure_label: str = ""
        self.auto_resolved: int = 0
        self.auto_resolve_method: str = ""
        self.coding_reviews: list[dict] = []
        self.error: bool = error


def _process_label(
    label_row: dict,
    rules: list[PostProcessorRule],
    ignore_texts: frozenset[str] = frozenset(),
) -> _LabelResult:
    """Call both LLM providers for one label and return a write-ready result.

    Runs inside the outer pool — spawns an inner 2-worker pool for the two
    provider calls so both happen concurrently within this worker thread.
    """
    label_id = str(label_row.get("label_id", ""))
    if not label_id:
        return _LabelResult("", error=True)

    text = str(label_row.get("text", ""))
    try:
        entities = json.loads(label_row.get("entities_json", "[]") or "[]")
    except json.JSONDecodeError:
        entities = []
    if rules:
        entities = apply_rules_to_entities(text, entities, rules)

    result = _LabelResult(label_id)

    try:
        if _stop_requested():
            result.error = True
            return result
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as inner:
            fut_aws = inner.submit(_call_model_for_label, "aws", text, entities)
            fut_azure = inner.submit(_call_model_for_label, "azure", text, entities)
            aws_rows = fut_aws.result()
            azure_rows = fut_azure.result()

        aws_by_idx: dict[int, dict] = {
            int(item.get("entity_index", -1)): item
            for item in aws_rows
            if isinstance(item, dict) and isinstance(item.get("entity_index"), int)
        }
        azure_by_idx: dict[int, dict] = {
            int(item.get("entity_index", -1)): item
            for item in azure_rows
            if isinstance(item, dict) and isinstance(item.get("entity_index"), int)
        }

        updated_entities = [dict(e) for e in entities]
        n_disagreements = 0
        auto_resolved_count = 0
        auto_resolve_methods: list[str] = []

        for idx, entity in enumerate(updated_entities):
            current_label = str(entity.get("label", "finding"))
            entity_text = str(entity.get("text", ""))
            aws_label = _normalise_label(
                str(aws_by_idx.get(idx, {}).get("suggested_label", current_label)),
                current_label,
            )
            azure_label = _normalise_label(
                str(azure_by_idx.get(idx, {}).get("suggested_label", current_label)),
                current_label,
            )
            aws_rationale = str(aws_by_idx.get(idx, {}).get("rationale", ""))
            azure_rationale = str(azure_by_idx.get(idx, {}).get("rationale", ""))
            aws_confidence = _safe_float(aws_by_idx.get(idx, {}).get("confidence"))
            azure_confidence = _safe_float(azure_by_idx.get(idx, {}).get("confidence"))

            if idx == 0:
                result.first_aws_label = aws_label
                result.first_azure_label = azure_label

            if aws_label == azure_label:
                entity["label"] = aws_label
            else:
                n_disagreements += 1

                # Fast path: deterministic rules can resolve many disagreements
                # without calling the terminology API or LLM tie-breaker.
                triage = _deterministic_resolve(
                    entity_text,
                    {aws_label, azure_label, current_label},
                    updated_entities,
                    idx,
                    model_a_label=aws_label,
                    model_b_label=azure_label,
                )
                if triage and triage.get("resolved_label") == "__suppress__":
                    entity["__suppress__"] = True
                    auto_resolved_count += 1
                    auto_resolve_methods.append("deterministic_rule")
                    continue

                if not triage:
                    triage = _auto_triage_disagreement(
                        encounter_text=text,
                        entity_text=entity_text,
                        current_label=current_label,
                        model_a_label=aws_label,
                        model_b_label=azure_label,
                        model_a_rationale=aws_rationale,
                        model_b_rationale=azure_rationale,
                    )
                if triage:
                    entity["label"] = triage["resolved_label"]
                    auto_resolved_count += 1
                    auto_resolve_methods.append(str(triage["method"]))
                    result.review_items.append(
                        {
                            "review_id": f"{label_id}:{idx}",
                            "entity_index": idx,
                            "entity_text": entity_text,
                            "current_label": current_label,
                            "model_a_label": aws_label,
                            "model_a_rationale": aws_rationale[:500],
                            "model_a_confidence": aws_confidence,
                            "model_b_label": azure_label,
                            "model_b_rationale": azure_rationale[:500],
                            "model_b_confidence": azure_confidence,
                            "auto_resolved": True,
                            "resolved_label": triage["resolved_label"],
                            "auto_resolve_method": triage["method"],
                            "auto_resolve_confidence": _safe_float(
                                triage.get("confidence")
                            ),
                            "auto_resolve_reason": str(triage.get("reason", ""))[:500],
                        }
                    )
                    continue

                result.review_items.append(
                    {
                        "review_id": f"{label_id}:{idx}",
                        "entity_index": idx,
                        "entity_text": entity_text,
                        "current_label": current_label,
                        "model_a_label": aws_label,
                        "model_a_rationale": aws_rationale[:500],
                        "model_a_confidence": aws_confidence,
                        "model_b_label": azure_label,
                        "model_b_rationale": azure_rationale[:500],
                        "model_b_confidence": azure_confidence,
                        "auto_resolved": False,
                    }
                )

        # Optionally append high-confidence "missing" spans proposed by either model.
        new_candidates: list[dict[str, Any]] = []
        for row in aws_rows + azure_rows:
            if not isinstance(row, dict):
                continue
            if not bool(row.get("is_new")):
                continue
            new_text = str(row.get("new_text") or row.get("text") or "").strip()
            suggested = _normalise_label(
                str(row.get("suggested_label", "finding")), "finding"
            )
            conf = _safe_float(row.get("confidence"))
            if not new_text or conf < 0.8:
                continue
            new_candidates.append({"text": new_text, "label": suggested})

        for cand in new_candidates:
            if any(
                str(e.get("text", "")).strip() == cand["text"]
                and str(e.get("label", "")).strip() == cand["label"]
                for e in updated_entities
            ):
                continue
            start = _resolve_start(text, cand["text"], around=0)
            if start is None:
                continue
            updated_entities.append(
                {
                    "text": cand["text"],
                    "label": cand["label"],
                    "start": start,
                    "end": start + len(cand["text"]),
                    "confidence": 0.8,
                }
            )

        updated_entities[:] = [e for e in updated_entities if not e.get("__suppress__")]

        # Unified post-processing stack (Layers 1-9).
        # Post-processor rules (Layer 1) were already applied before LLM
        # verification, so we pass rules=None here to avoid double-applying.
        updated_entities[:] = run_post_processing(
            text,
            updated_entities,
            rules=None,
            enable_disorder_gate=True,
            coding_mode=_CODING_MODE,
        )

        coding_reviews = _check_terminology_coding(
            label_id, updated_entities, ignore_texts
        )
        result.coding_reviews = coding_reviews

        total_entities = max(len(entities), 1)
        result.updated_entities = updated_entities
        result.n_disagreements = n_disagreements
        result.quality_score = max(
            0.0, min(1.0, (total_entities - n_disagreements) / total_entities)
        )
        result.agreement = n_disagreements == 0
        result.auto_resolved = auto_resolved_count
        if auto_resolve_methods:
            unique_methods = sorted(set(auto_resolve_methods))
            result.auto_resolve_method = ",".join(unique_methods)

    except Exception:
        logger.warning("Label processing failed label_id=%s", label_id, exc_info=True)
        result.error = True

    return result


# ---------------------------------------------------------------------------
# LLM re-extraction (for re_extract mode)
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

_EXTRACTION_SNOMED_TAG_TO_LABEL = {
    "qualifier value": "qualifier_value",
    "observable entity": "observable_entity",
    "body structure": "body_structure",
    "tumor staging": "tumor_staging",
    "assessment scale": "assessment_scale",
    "staging scale": "staging_scale",
    "regime/therapy": "regime_therapy",
    "record artifact": "record_artifact",
    "physical object": "physical_object",
    "morphologic abnormality": "morphologic_abnormality",
    "clinical drug": "clinical_drug",
    "medicinal product": "medicinal_product",
    "qualifier": "qualifier_value",
}


def _re_extract_entities(text: str) -> list[dict[str, Any]] | None:
    """Run LLM extraction over encounter text and return canonical entity dicts.

    Returns None on failure so the caller can skip without losing progress.
    """
    if not text or not text.strip():
        return []

    # Split into sentences (regex mode -- no spacy dependency in the API service)
    parts = _SENTENCE_SPLIT_RE.split(text)
    sentences: list[dict[str, Any]] = []
    offset = 0
    for idx, part in enumerate(parts):
        stripped = part.strip()
        if not stripped:
            offset += len(part) + 1
            continue
        start = text.find(stripped, offset)
        if start < 0:
            start = offset
        end = start + len(stripped)
        sentences.append(
            {"sentence_id": f"s{idx}", "text": stripped, "start": start, "end": end}
        )
        offset = end

    if not sentences:
        return []

    cfg = get_prompt_config("extraction", version=1)
    from libs.pipeline_graph.subgraphs._extractor import assemble_system_prompt

    extraction_prompt = assemble_system_prompt(
        instructions=str(cfg.get("systemPrompt") or ""),
        output_schema_json=cfg.get("outputSchema"),
        few_shot_examples=cfg.get("fewShotExamples") or [],
    )
    user_payload = (
        f"Extract clinical entities from sentences below.\n\n"
        f"Encounter text:\n{text}\n\n"
        f"Sentences:\n{json.dumps([{'sentence_id': s['sentence_id'], 'text': s['text']} for s in sentences], ensure_ascii=False)}"
    )

    client = create_llm(provider="aws", tier="small")
    for attempt in range(_LLM_RETRIES + 1):
        if _stop_requested():
            return None
        _llm_limiter.acquire()
        try:
            response = client.converse(
                system=extraction_prompt,
                messages=[{"role": "user", "content": user_payload}],
                max_tokens=2048,
                temperature=0.0,
                agent_task="label_verifier_extraction",
            )
            break
        except Exception as exc:
            msg = str(exc).lower()
            throttled = any(
                m in msg for m in ("429", "rate limit", "throttle", "too many requests")
            )
            if throttled:
                _llm_limiter.on_throttle()
            if attempt >= _LLM_RETRIES:
                logger.warning("Re-extraction LLM call failed: %s", exc)
                return None
            delay = _LLM_BACKOFF_BASE_S * (2**attempt)
            if throttled:
                delay *= 2.0
            time.sleep(delay)
        finally:
            _llm_limiter.release()
    else:
        return None

    _llm_limiter.on_success()
    parsed = _parse_model_json(response.text)
    sent_map = {s["sentence_id"]: s for s in sentences}
    entities: list[dict[str, Any]] = []

    for row in parsed.get("terms", []):
        if not isinstance(row, dict):
            continue
        sid = str(row.get("sentence_id", "")).strip()
        term_text = str(row.get("text", "")).strip()
        if not sid or not term_text:
            continue
        sent = sent_map.get(sid)
        if not sent:
            continue

        assertion = str(row.get("assertion", "present")).strip().lower()
        if assertion not in {
            "present",
            "absent",
            "refuted",
            "possible",
            "historical",
            "planned",
            "hypothetical",
            "family",
            "declined",
            "cancelled",
        }:
            assertion = "present"

        tag = str(row.get("semantic_tag", "finding")).strip().lower()
        label = _EXTRACTION_SNOMED_TAG_TO_LABEL.get(tag, tag.replace(" ", "_"))

        start = _resolve_start(text, term_text, around=sent["start"])
        if start is None:
            start = sent["start"]
        end = start + len(term_text)

        entity: dict[str, Any] = {
            "text": term_text,
            "label": label,
            "start": start,
            "end": end,
            "assertion": assertion,
        }

        lookup_term = str(row.get("lookup_term", "")).strip()
        if lookup_term and lookup_term != term_text:
            entity["lookup_term"] = lookup_term

        value = str(row.get("value", "") or "").strip()
        unit = str(row.get("unit", "") or "").strip()
        ref_range = str(row.get("reference_range", "") or "").strip()
        if value:
            entity["value"] = value
        if unit:
            entity["unit"] = unit
        if ref_range:
            entity["reference_range"] = ref_range

        entities.append(entity)

    return entities


def _run_re_extraction_phase(labels: list[dict[str, Any]]) -> int:
    """Phase 0 for re_extract mode: LLM-extract entities for all labels.

    Updates entities_json in Neo4j and mutates the label dicts in place.
    Returns the number of labels successfully re-extracted.
    """
    logger.info("Re-extraction phase: %d labels", len(labels))
    write_client = PatientGraphClient()
    extracted = 0
    errors = 0

    try:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=_MAX_WORKERS,
            thread_name_prefix="re-extract",
        ) as pool:
            futures = {
                pool.submit(_re_extract_entities, str(row.get("text", ""))): row
                for row in labels
            }
            for future in concurrent.futures.as_completed(futures):
                if _stop_requested():
                    break
                row = futures[future]
                label_id = str(row.get("label_id", ""))
                try:
                    entities = future.result()
                except Exception:
                    logger.warning(
                        "Re-extraction future failed for %s",
                        label_id[:8],
                        exc_info=True,
                    )
                    errors += 1
                    continue

                if entities is None:
                    errors += 1
                    continue

                entities_json = json.dumps(entities)
                row["entities_json"] = entities_json
                try:
                    with write_client.session() as session:
                        session.run(
                            UPDATE_TRAINING_LABEL_ENTITIES,
                            label_id=label_id,
                            entities_json=entities_json,
                        )
                except Exception:
                    logger.warning(
                        "Neo4j write failed during re-extraction for %s",
                        label_id[:8],
                        exc_info=True,
                    )
                    errors += 1
                    continue

                extracted += 1
                if extracted % 100 == 0:
                    logger.info(
                        "Re-extraction progress: %d/%d extracted, %d errors",
                        extracted,
                        len(labels),
                        errors,
                    )
    finally:
        write_client.close()

    logger.info(
        "Re-extraction phase complete: %d extracted, %d errors", extracted, errors
    )
    return extracted


# ---------------------------------------------------------------------------
# Neo4j write helper (per-result, uses client-level retry)
# ---------------------------------------------------------------------------


def _write_result_to_graph(client: "PatientGraphClient", result: _VerifyResult) -> None:
    """Persist verification output for a single label to Neo4j.

    Uses ``client.run()`` which opens a fresh session per call and retries
    on transient connection errors (ServiceUnavailable, SessionExpired, etc.).
    """
    for item in result.review_items:
        client.run(
            UPSERT_LABEL_VERIFICATION_REVIEW,
            review_id=item["review_id"],
            label_id=result.label_id,
            entity_index=item["entity_index"],
            entity_text=item["entity_text"],
            current_label=item["current_label"],
            model_a_label=item["model_a_label"],
            model_a_rationale=item["model_a_rationale"],
            model_a_confidence=item.get("model_a_confidence", 0.0),
            model_b_label=item["model_b_label"],
            model_b_rationale=item["model_b_rationale"],
            model_b_confidence=item.get("model_b_confidence", 0.0),
            auto_resolve_method=item.get("auto_resolve_method"),
            auto_resolve_confidence=item.get("auto_resolve_confidence"),
            auto_resolve_reason=item.get("auto_resolve_reason"),
        )
        if item.get("auto_resolved"):
            resolved_label = str(item.get("resolved_label", ""))
            client.run(
                RESOLVE_LABEL_VERIFICATION_REVIEW,
                review_id=item["review_id"],
                resolved_label=resolved_label,
                reviewer=f"auto_triage:{item.get('auto_resolve_method', 'unknown')}",
                entities_json=json.dumps(result.updated_entities),
                model_a_was_correct=(item["model_a_label"] == resolved_label),
                model_b_was_correct=(item["model_b_label"] == resolved_label),
            )

    for cr in result.coding_reviews:
        client.run(
            UPSERT_CODING_REVIEW,
            review_id=cr["review_id"],
            label_id=result.label_id,
            entity_index=cr["entity_index"],
            entity_text=cr["entity_text"],
            entity_label=cr["entity_label"],
            coded=cr["coded"],
            snomed_concept_id=cr.get("snomed_concept_id"),
            snomed_term=cr.get("snomed_term"),
            score=cr.get("score"),
            semantic_tag=cr.get("semantic_tag"),
            assertion=cr.get("assertion", "present"),
            decision_tier=cr.get("decision_tier"),
            tier_reason=cr.get("tier_reason"),
            tier_decision=cr.get("tier_decision"),
            suggested_label=cr.get("suggested_label"),
            tag_mismatch_delta=cr.get("tag_mismatch_delta"),
        )

    client.run(
        UPDATE_TRAINING_LABEL_ENTITIES,
        label_id=result.label_id,
        entities_json=json.dumps(result.updated_entities),
    )
    client.run(
        UPDATE_LABEL_VERIFICATION,
        label_id=result.label_id,
        verification_agreement=result.agreement,
        model_a_label=result.first_aws_label,
        model_b_label=result.first_azure_label,
        quality_score=result.quality_score,
    )


# ---------------------------------------------------------------------------
# Main verification entry point
# ---------------------------------------------------------------------------


def run_verification() -> None:
    """Run full label verification job with parallel LLM calls.

    Phase 1 — Fetch all included TrainingLabel rows from Neo4j (one read session).
    Phase 2 — Process all labels concurrently via _MAX_WORKERS threads, each
               calling AWS + Azure in a nested 2-thread pool.
    Phase 3 — Write results back to Neo4j sequentially as futures complete
               (avoids multi-threaded session usage).

    Neo4j writes use ``write_client.run()`` (fresh session per call with
    automatic retry on transient errors). If all retries fail for a single
    label the write is skipped and the label counted as an error so the
    pipeline continues rather than stalling.
    """
    # ------------------------------------------------------------------
    # Phase 1: fetch
    # ------------------------------------------------------------------
    state = get_job_state()
    run_mode = str(state.get("run_mode") or "all")

    fetch_client = PatientGraphClient()
    try:
        with fetch_client.session() as session:
            rules = parse_rules(
                [dict(r) for r in session.run(GET_ACTIVE_POST_PROCESSOR_RULES)]
            )
            ignore_texts = frozenset(
                str(r["entity_text"])
                for r in session.run(GET_CODING_IGNORE_RULES)
                if r.get("entity_text")
            )
            logger.info("Loaded %d coding ignore rules", len(ignore_texts))
            rows = session.run(GET_ALL_INCLUDED_LABELS_FOR_EXPORT)
            labels = [dict(r) for r in rows]
            if run_mode == "hitl_only":
                reviewed = session.run(GET_HITL_REVIEWED_LABEL_IDS)
                reviewed_ids = {
                    str(r["label_id"]) for r in reviewed if r.get("label_id")
                }
                labels = [
                    row
                    for row in labels
                    if str(row.get("label_id", "")) in reviewed_ids
                ]
            elif run_mode == "resume":
                before = len(labels)
                labels = [row for row in labels if not row.get("verified_at")]
                skipped = before - len(labels)
                logger.info("Resume mode: skipping %d already-verified labels", skipped)
    finally:
        fetch_client.close()

    _patch_state(total=len(labels))
    logger.info(
        "Label verification started: %d labels, max_workers=%d (~%d concurrent LLM requests)",
        len(labels),
        _MAX_WORKERS,
        _MAX_WORKERS * 2,
    )

    # ------------------------------------------------------------------
    # Phase 1b (optional): re-extract entities via LLM before verification
    # ------------------------------------------------------------------
    if run_mode == "re_extract" and not _stop_requested():
        logger.info("Re-extract mode: running LLM extraction before verification")
        _run_re_extraction_phase(labels)

    # ------------------------------------------------------------------
    # Phase 2 + 3: process in parallel, write sequentially as futures land
    # ------------------------------------------------------------------
    write_client = PatientGraphClient()
    try:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=_MAX_WORKERS,
            thread_name_prefix="label-verify",
        ) as pool:
            futures = {
                pool.submit(_process_label, row, rules, ignore_texts): row
                for row in labels
            }
            last_progress_log_done = 0

            for future in concurrent.futures.as_completed(futures):
                if _stop_requested():
                    break
                try:
                    result = future.result()
                except Exception:
                    logger.warning("Future raised unexpectedly", exc_info=True)
                    _increment_state(done=1, errors=1)
                    continue

                if result.error or not result.label_id:
                    _increment_state(done=1, errors=1)
                    continue

                try:
                    _write_result_to_graph(write_client, result)
                except Exception:
                    logger.warning(
                        "Neo4j write failed for label %s after retries — skipping",
                        result.label_id,
                        exc_info=True,
                    )
                    _increment_state(done=1, errors=1)
                    continue

                _increment_state(
                    done=1,
                    agreements=(1 if result.agreement else 0),
                    disagreements=result.n_disagreements,
                    auto_resolved=result.auto_resolved,
                    pending_review=sum(
                        1
                        for item in result.review_items
                        if not item.get("auto_resolved")
                    ),
                )
                state_now = get_job_state()
                done_now = int(state_now.get("done") or 0)
                total_now = int(state_now.get("total") or 0)
                log_step = 25 if total_now <= 1000 else 100
                if (
                    done_now >= total_now
                    or done_now - last_progress_log_done >= log_step
                ):
                    eta_seconds = state_now.get("eta_seconds")
                    eta_str = (
                        f"{eta_seconds}s" if isinstance(eta_seconds, int) else "unknown"
                    )
                    logger.info(
                        "Verifier progress: %d/%d (%.2f%%), remaining=%d, throughput=%.2f items/min, eta=%s",
                        done_now,
                        total_now,
                        float(state_now.get("progress_pct") or 0.0),
                        int(state_now.get("remaining") or 0),
                        float(state_now.get("items_per_min") or 0.0),
                        eta_str,
                    )
                    last_progress_log_done = done_now

        _patch_state(
            status=("cancelled" if _stop_requested() else "done"),
            finished_at=time.time(),
        )
        logger.info("Label verification completed")

    except Exception as exc:
        logger.exception("Label verification failed")
        _patch_state(status="failed", finished_at=time.time(), last_error=str(exc))
    finally:
        write_client.close()
