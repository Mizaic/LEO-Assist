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

import httpx
from libs.cypher.coding_review_queries import GET_CODING_IGNORE_RULES, UPSERT_CODING_REVIEW
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
from libs.llm_client.factory import LLMResponse, create_llm
from libs.neo4j_client.client import PatientGraphClient
from libs.ner.context_detector import apply_context_detection
from libs.ner.observable_post_processor import normalize_observable_entities
from libs.ner.post_processor_rules import apply_rules_to_entities, parse_rules, PostProcessorRule
from libs.prompts.registry import get_prompt

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

# Number of labels processed concurrently.
# Each worker runs AWS+Azure in parallel, so in-flight LLM requests are roughly 2x this value.
# For large backfills (e.g., 12k labels), tune LABEL_VERIFY_WORKERS via env for your infra limits.
_MAX_WORKERS = int(os.getenv("LABEL_VERIFY_WORKERS", "50"))
_TERMINOLOGY_API_URL = os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001").rstrip("/")
_AUTO_TRIAGE_TERM_THRESHOLD = float(os.getenv("AUTO_TRIAGE_TERM_THRESHOLD", "0.85"))
_AUTO_TRIAGE_LLM_THRESHOLD = float(os.getenv("AUTO_TRIAGE_LLM_THRESHOLD", "0.80"))
_LLM_RETRIES = int(os.getenv("LABEL_VERIFY_LLM_RETRIES", "4"))
_LLM_BACKOFF_BASE_S = float(os.getenv("LABEL_VERIFY_LLM_BACKOFF_BASE_S", "0.6"))


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return max(minimum, default)


_ADAPTIVE_MIN_CONCURRENCY = _env_int("LABEL_VERIFY_ADAPTIVE_MIN_CONCURRENCY", 20, minimum=1)
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
            return {"target": self._target, "in_flight": self._in_flight, "min": self._min, "max": self._max}


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
    """
    mode = run_mode if run_mode in {"all", "hitl_only", "resume"} else "all"
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
            )
            parsed = _parse_model_json(response.text)
            entity_rows = parsed.get("entities", [])
            _llm_limiter.on_success()
            return entity_rows if isinstance(entity_rows, list) else []
        except Exception as exc:
            msg = str(exc).lower()
            throttled = any(
                marker in msg for marker in ("429", "rate limit", "ratelimit", "throttle", "too many requests")
            )
            if throttled:
                _llm_limiter.on_throttle()
            if attempt >= _LLM_RETRIES:
                logger.warning("Label verification model call failed provider=%s", provider, exc_info=True)
                return []
            delay = _LLM_BACKOFF_BASE_S * (2 ** attempt)
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


def _clean_observable_spans(encounter_text: str, updated_entities: list[dict[str, Any]]) -> None:
    """Normalize observable spans to test-name boundaries with structured values."""
    cleaned = normalize_observable_entities(
        encounter_text,
        updated_entities,
        add_qualifier_value=True,
    )
    updated_entities[:] = cleaned


_VALUE_UNIT_RE = re.compile(
    r"(?P<value>[<>]?\s*\d+(?:\.\d+)?)\s*(?P<unit>(?:10\^\d+\/[A-Za-z]+|[A-Za-z/%]+(?:\/[A-Za-z]+)*))",
    re.IGNORECASE,
)

_LAB_UNIT_INDICATORS = re.compile(
    r"(?:mmol|umol|nmol|pmol|mg|ug|ng|pg|g|iu|mL|miu|L|mol|fl|10\^9|%|ratio|kg|kpa|mmhg|bpm|ug/g|cigs)",
    re.IGNORECASE,
)

_RESULT_DESCRIPTOR_TEXTS = frozenset({
    "abnormal", "abnormal but expected", "normal", "satisfactory",
    "outside reference range", "within normal limits", "within reference range",
    "normal - no action", "borderline", "high", "low", "raised", "elevated",
    "nad", "no abnormality detected", "fobt non-response", "non-response",
    "no problems or concerns", "no problemds or concerns",
    "negative", "positive", "reactive", "non-reactive",
    "but expected", "weight stable",
})

_EPISODE_MARKER_TEXTS = frozenset({
    "new episode", "ongoing episode", "first episode",
})

_LIFESTYLE_FACTOR_TEXTS = frozenset({
    "diet", "alcohol", "exercise", "weight", "smoking", "drives",
    "sleep", "caffeine",
})

_UNCERTAINTY_MARKER_RE = re.compile(r"^\?{1,4}$")

_SEVERITY_MODIFIER_TEXTS = frozenset({
    "severe", "mild", "moderate", "minor", "major", "urgent",
    "worsened", "worsening", "improving", "stable", "unchanged",
    "pale", "slight", "significant", "marked",
})

_MDT_OUTCOME_RE = re.compile(
    r"(?:mdt|multidisciplinary)\s+(?:meet(?:ing)?|discussion|team)?\s*(?:outcome|result|decision)",
    re.IGNORECASE,
)

_SMOKING_CONSUMPTION_RE = re.compile(
    r"\d+[\s-]*(?:\d+)?\s*(?:cigs?|cigarettes?|roll[\s-]?ups?)\s*/\s*(?:day|week|wk)",
    re.IGNORECASE,
)

_REF_RANGE_ONLY_RE = re.compile(
    r"^\s*\[?\s*\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\s*\]?\s*$",
)

_ANALYTE_NAMES = frozenset({
    "creatinine", "albumin", "phosphate", "inorganic phosphate", "sodium",
    "potassium", "calcium", "bilirubin", "cholesterol", "glucose", "urea",
    "ferritin", "haemoglobin", "globulin", "triglyceride", "triglycerides",
    "folate", "iron", "zinc", "magnesium", "copper", "lithium",
    "testosterone", "oestradiol", "cortisol", "thyroxine",
    "chloride", "bicarbonate", "protein", "alkaline phosphatase",
})

_BARE_NUMERIC_RE = re.compile(r"^[<>]?\s*\d+(?:\.\d+)?\s*$")


def _is_smoking_status_text(text: str) -> bool:
    lowered = text.strip().lower()
    return "smoking status" in lowered or lowered in {
        "smoker", "non-smoker", "ex-smoker", "never smoker",
        "current smoker", "ex smoker", "non smoker",
    }


def _is_lab_value_text(text: str) -> bool:
    """True if text looks like a lab result value+unit, not a medication dose."""
    stripped = text.strip()
    if not stripped:
        return False
    starts_with_number = bool(re.match(r"^[<>]?\s*\d", stripped))
    has_lab_unit = bool(_LAB_UNIT_INDICATORS.search(stripped))
    return starts_with_number and has_lab_unit


def _is_numeric_measurement_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    starts_with_number = bool(re.match(r"^[<>]?\s*\d", stripped))
    has_unit = bool(_VALUE_UNIT_RE.search(stripped))
    return starts_with_number and has_unit


def _is_result_descriptor(text: str) -> bool:
    return text.strip().lower() in _RESULT_DESCRIPTOR_TEXTS


def _is_bare_analyte(text: str) -> bool:
    return text.strip().lower() in _ANALYTE_NAMES


def _extract_value_unit(text: str) -> tuple[str, str] | None:
    m = _VALUE_UNIT_RE.search(text or "")
    if not m:
        return None
    value = (m.group("value") or "").strip()
    unit = (m.group("unit") or "").strip()
    if not value or not unit:
        return None
    return value, unit


def _has_nearby_observable(entities: list[dict[str, Any]], target_idx: int, max_dist: int = 80) -> bool:
    target = entities[target_idx]
    t_start = int(target.get("start", 0) or 0)
    t_end = int(target.get("end", 0) or 0)
    for i, ent in enumerate(entities):
        if i == target_idx:
            continue
        if str(ent.get("label", "")) != "observable_entity":
            continue
        o_start = int(ent.get("start", 0) or 0)
        o_end = int(ent.get("end", 0) or 0)
        dist = min(abs(t_start - o_end), abs(o_start - t_end))
        if dist <= max_dist:
            return True
    return False


def _normalise_entity_types(updated_entities: list[dict[str, Any]]) -> None:
    """Apply deterministic cleanup rules after model voting."""

    for ent in updated_entities:
        label = str(ent.get("label", ""))
        text = str(ent.get("text", ""))
        lowered = text.strip().lower()

        # 1) Smoking status → finding (not attribute or situation).
        if label in {"attribute", "situation"} and _is_smoking_status_text(text):
            ent["label"] = "finding"

        # 2) Lab result values labeled X_DOSAGE → qualifier_value.
        if label == "X_DOSAGE" and _is_lab_value_text(text):
            ent["label"] = "qualifier_value"

        # 3) Numeric-only observable snippets → qualifier_value.
        if label == "observable_entity" and _is_numeric_measurement_text(text):
            ent["label"] = "qualifier_value"

        # 4) Result descriptors → qualifier_value (from finding or situation).
        if label in {"finding", "situation"} and _is_result_descriptor(text):
            ent["label"] = "qualifier_value"

        # 5) Episode markers → qualifier_value (from X_TEMPORAL or X_PATHWAY_MILESTONE).
        if label in {"X_TEMPORAL", "X_PATHWAY_MILESTONE"} and lowered in _EPISODE_MARKER_TEXTS:
            ent["label"] = "qualifier_value"

        # 5b) Remaining X_PATHWAY_MILESTONE → procedure (pathway analytics handled downstream).
        if label == "X_PATHWAY_MILESTONE" and ent.get("label") == "X_PATHWAY_MILESTONE":
            ent["label"] = "procedure"

        # 6) Lifestyle factors as attribute → finding.
        if label == "attribute" and lowered in _LIFESTYLE_FACTOR_TEXTS:
            ent["label"] = "finding"

        # 7) Smoking consumption frequency as X_DOSAGE → qualifier_value.
        if label == "X_DOSAGE" and _SMOKING_CONSUMPTION_RE.search(text):
            ent["label"] = "qualifier_value"

        # 8) Uncertainty markers (??, ???) → qualifier_value.
        if _UNCERTAINTY_MARKER_RE.match(text.strip()):
            ent["label"] = "qualifier_value"

        # 9) Severity/modifier words → qualifier_value (from attribute or finding).
        if label in {"attribute", "finding"} and lowered in _SEVERITY_MODIFIER_TEXTS:
            ent["label"] = "qualifier_value"

        # 10) MDT outcome heading phrases → record_artifact.
        if _MDT_OUTCOME_RE.search(text):
            ent["label"] = "record_artifact"
        elif lowered == "mdt" and label in {"event", "record_artifact"}:
            ent["label"] = "procedure"

    # ── Suppression passes (modify the list in place) ──

    suppress_indices: set[int] = set()
    for i, ent in enumerate(updated_entities):
        label = str(ent.get("label", ""))
        text = str(ent.get("text", ""))

        # 11) Bare analyte names near an observable → suppress.
        if label == "substance" and _is_bare_analyte(text) and _has_nearby_observable(updated_entities, i):
            suppress_indices.add(i)

        # 14) X_NEGATION_CUE entities → suppress (negation handled by context detector).
        if label == "X_NEGATION_CUE":
            suppress_indices.add(i)

        # 12) Reference-range-only spans → suppress.
        if _REF_RANGE_ONLY_RE.match(text):
            suppress_indices.add(i)

    # 13) Duplicate and sub-span overlap suppression.
    for i, ent_a in enumerate(updated_entities):
        if i in suppress_indices:
            continue
        a_label = str(ent_a.get("label", ""))
        a_start = int(ent_a.get("start", 0) or 0)
        a_end = int(ent_a.get("end", 0) or 0)
        a_text = str(ent_a.get("text", "")).strip().lower()
        for j, ent_b in enumerate(updated_entities):
            if j <= i or j in suppress_indices:
                continue
            b_label = str(ent_b.get("label", ""))
            b_start = int(ent_b.get("start", 0) or 0)
            b_end = int(ent_b.get("end", 0) or 0)
            b_text = str(ent_b.get("text", "")).strip().lower()

            # Exact duplicate (same text + same label).
            if a_text == b_text and a_label == b_label:
                suppress_indices.add(j)
                continue

            # Same-label containment: suppress the shorter span.
            if a_label == b_label:
                if a_start <= b_start and a_end >= b_end:
                    suppress_indices.add(j)
                elif b_start <= a_start and b_end >= a_end:
                    suppress_indices.add(i)

    if suppress_indices:
        updated_entities[:] = [e for i, e in enumerate(updated_entities) if i not in suppress_indices]


def _link_observable_value_units(updated_entities: list[dict[str, Any]]) -> None:
    """Attach value/unit from nearby numeric spans onto observable entities."""
    observable_indices = [
        i for i, e in enumerate(updated_entities)
        if str(e.get("label", "")) == "observable_entity"
    ]
    if not observable_indices:
        return

    measurement_indices = [
        i for i, e in enumerate(updated_entities)
        if _is_numeric_measurement_text(str(e.get("text", "")))
    ]
    if not measurement_indices:
        return

    for obs_i in observable_indices:
        obs = updated_entities[obs_i]
        if obs.get("value") is not None and obs.get("unit"):
            continue
        obs_start = int(obs.get("start", 0) or 0)
        obs_end = int(obs.get("end", 0) or 0)
        closest_idx: int | None = None
        closest_dist: int | None = None

        for meas_i in measurement_indices:
            meas = updated_entities[meas_i]
            meas_start = int(meas.get("start", 0) or 0)
            meas_end = int(meas.get("end", 0) or 0)
            # Prefer measurements adjacent to the observable phrase.
            dist = min(abs(meas_start - obs_end), abs(obs_start - meas_end))
            if closest_dist is None or dist < closest_dist:
                closest_dist = dist
                closest_idx = meas_i

        if closest_idx is None or (closest_dist is not None and closest_dist > 40):
            continue
        parsed = _extract_value_unit(str(updated_entities[closest_idx].get("text", "")))
        if not parsed:
            continue
        value, unit = parsed
        obs["value"] = value
        obs["unit"] = unit


_CLINICAL_LABELS = frozenset({
    "disorder", "finding", "procedure", "observable_entity", "qualifier_value",
    "substance", "medicinal_product", "clinical_drug", "situation", "event",
    "body_structure", "tumor_staging", "assessment_scale", "staging_scale",
    "regime_therapy", "record_artifact", "morphologic_abnormality",
    "occupation", "attribute", "environment", "product",
})


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
    _real_negation_words = {"no", "not", "denies", "denied", "nil", "without", "never", "none", "neither", "nor"}
    is_real_negation = lowered in _real_negation_words
    if not is_real_negation:
        if model_a_label == "X_NEGATION_CUE" and model_b_label in _CLINICAL_LABELS:
            return {"resolved_label": model_b_label, "confidence": 0.95,
                    "method": "deterministic_rule", "reason": "X_NEGATION_CUE misuse — prefer clinical label"}
        if model_b_label == "X_NEGATION_CUE" and model_a_label in _CLINICAL_LABELS:
            return {"resolved_label": model_a_label, "confidence": 0.95,
                    "method": "deterministic_rule", "reason": "X_NEGATION_CUE misuse — prefer clinical label"}

    # Numeric measurement labeled observable_entity by one model → qualifier_value.
    if "qualifier_value" in candidates:
        if _is_numeric_measurement_text(text):
            return {"resolved_label": "qualifier_value", "confidence": 0.99,
                    "method": "deterministic_rule", "reason": "numeric measurement value"}
        if _BARE_NUMERIC_RE.match(text):
            return {"resolved_label": "qualifier_value", "confidence": 0.99,
                    "method": "deterministic_rule", "reason": "bare numeric value"}
        if _is_lab_value_text(text):
            return {"resolved_label": "qualifier_value", "confidence": 0.99,
                    "method": "deterministic_rule", "reason": "lab result value"}
        if _is_result_descriptor(text):
            return {"resolved_label": "qualifier_value", "confidence": 0.99,
                    "method": "deterministic_rule", "reason": "result descriptor"}
        if lowered in _EPISODE_MARKER_TEXTS:
            return {"resolved_label": "qualifier_value", "confidence": 0.99,
                    "method": "deterministic_rule", "reason": "episode marker"}
        if lowered in _SEVERITY_MODIFIER_TEXTS:
            return {"resolved_label": "qualifier_value", "confidence": 0.99,
                    "method": "deterministic_rule", "reason": "severity modifier"}
        if _UNCERTAINTY_MARKER_RE.match(text):
            return {"resolved_label": "qualifier_value", "confidence": 0.99,
                    "method": "deterministic_rule", "reason": "uncertainty marker"}

    # Smoking / lifestyle attribute → finding.
    if "finding" in candidates:
        if _is_smoking_status_text(text):
            return {"resolved_label": "finding", "confidence": 0.99,
                    "method": "deterministic_rule", "reason": "smoking status"}
        if lowered in _LIFESTYLE_FACTOR_TEXTS:
            return {"resolved_label": "finding", "confidence": 0.99,
                    "method": "deterministic_rule", "reason": "lifestyle factor"}

    # Bare analyte near observable → suppress (return special marker).
    if _is_bare_analyte(text) and _has_nearby_observable(all_entities, entity_idx):
        return {"resolved_label": "__suppress__", "confidence": 0.99,
                "method": "deterministic_rule", "reason": "bare analyte near observable"}

    # Smoking consumption frequency → qualifier_value.
    if "qualifier_value" in candidates and _SMOKING_CONSUMPTION_RE.search(text):
        return {"resolved_label": "qualifier_value", "confidence": 0.99,
                "method": "deterministic_rule", "reason": "smoking consumption frequency"}

    # MDT → procedure.
    if "procedure" in candidates and lowered == "mdt":
        return {"resolved_label": "procedure", "confidence": 0.99,
                "method": "deterministic_rule", "reason": "MDT is procedure"}

    # MDT outcome heading → record_artifact.
    if _MDT_OUTCOME_RE.search(text):
        return {"resolved_label": "record_artifact", "confidence": 0.99,
                "method": "deterministic_rule", "reason": "MDT outcome heading"}

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

    # 1) Terminology resolution path.
    try:
        with httpx.Client(timeout=8) as client:
            response = client.post(
                f"{_TERMINOLOGY_API_URL}/terminology/resolve",
                json={"terms": [entity_text]},
            )
            response.raise_for_status()
            payload = response.json() if response.content else {}
    except Exception:
        logger.debug("Auto-triage terminology lookup failed for %r", entity_text, exc_info=True)
        payload = {}

    candidates = (((payload or {}).get("results") or {}).get(entity_text) or [])
    if candidates and isinstance(candidates, list):
        top = candidates[0] if isinstance(candidates[0], dict) else {}
        top_score = _safe_float(top.get("score"))
        top_tag = str(top.get("semantic_tag") or "")
        top_label = _snomed_tag_to_label(top_tag)
        logger.debug(
            "Auto-triage term lookup: entity=%r score=%.2f tag=%r mapped=%r targets=%r",
            entity_text, top_score, top_tag, top_label, target_labels,
        )
        if (
            top_score >= _AUTO_TRIAGE_TERM_THRESHOLD
            and top_label in target_labels
        ):
            return {
                "resolved_label": top_label,
                "confidence": top_score,
                "method": "terminology_api",
                "reason": f"top semantic tag {top_tag!r} score={top_score:.2f}",
            }

    # 2) LLM tie-break path.
    try:
        client = create_llm(provider="aws", tier="small")
        response: LLMResponse = client.converse(
            system=get_prompt("label_disambiguation", version=1),
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "entity_text": entity_text,
                            "encounter_text": encounter_text,
                            "current_label": current_label,
                            "model_a_label": model_a_label,
                            "model_a_rationale": model_a_rationale,
                            "model_b_label": model_b_label,
                            "model_b_rationale": model_b_rationale,
                            "allowed_labels": sorted(VALID_ENTITY_LABELS),
                        }
                    ),
                }
            ],
            temperature=0.0,
            max_tokens=350,
        )
        parsed = _parse_model_json(response.text)
    except Exception:
        logger.warning("Auto-triage LLM tie-break failed for %r", entity_text, exc_info=True)
        parsed = {}

    resolved_label = _normalise_label(str(parsed.get("resolved_label", current_label)), current_label)
    confidence = _safe_float(parsed.get("confidence"))
    reason = str(parsed.get("reason", ""))[:500]
    logger.debug(
        "Auto-triage LLM tie-break: entity=%r resolved=%r conf=%.2f targets=%r threshold=%.2f",
        entity_text, resolved_label, confidence, target_labels, _AUTO_TRIAGE_LLM_THRESHOLD,
    )
    if resolved_label in target_labels and confidence >= _AUTO_TRIAGE_LLM_THRESHOLD:
        return {
            "resolved_label": resolved_label,
            "confidence": confidence,
            "method": "llm_tiebreak",
            "reason": reason,
        }
    return None


_CODEABLE_LABELS = frozenset({
    "disorder", "finding", "procedure", "observable_entity", "substance",
    "medicinal_product", "clinical_drug", "situation", "body_structure",
    "morphologic_abnormality", "regime_therapy", "assessment_scale",
    "tumor_staging", "organism", "occupation", "physical_object",
})

_CODING_SCORE_THRESHOLD = float(os.getenv("CODING_REVIEW_SCORE_THRESHOLD", "0.70"))
_CODING_ALT_LOW = float(os.getenv("CODING_ALT_THRESHOLD_LOW", "0.3"))
_CODING_ALT_ENABLED = os.getenv("CODING_ALT_ENABLED", "true").lower() == "true"


def _resolve_terms_via_api(terms: list[str]) -> dict[str, list]:
    """POST a batch of terms to the terminology resolve endpoint."""
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                f"{_TERMINOLOGY_API_URL}/terminology/resolve",
                json={"terms": terms},
            )
            resp.raise_for_status()
            payload = resp.json() if resp.content else {}
            return (payload or {}).get("results") or {}
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
        )
        raw_text = response.text.strip()
        match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if not match:
            logger.debug("Alt-term LLM: no JSON array for %r -- response: %s", term, raw_text[:120])
            return []
        raw = json.loads(match.group())
        seen_lower = term.strip().lower()
        alts = [
            s.strip() for s in raw
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
        logger.info("LLM-alt (verify): no alternatives suggested for %r (%s)", term, entity_label)
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
            term, alt, top.get("snomed_concept_id", ""), score,
        )
        if score >= _CODING_SCORE_THRESHOLD and score > best_score:
            best_score = score
            best = top
    if best:
        logger.info(
            "LLM-alt (verify): RESOLVED %r -> %r (%.4f)",
            term, best.get("snomed_term"), best_score,
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
) -> dict[str, Any]:
    """Assemble a coding review dict for the queue."""
    concept_id = str(top.get("snomed_concept_id") or "")
    return {
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
    }


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
    """
    codeable = [
        (i, e) for i, e in enumerate(entities)
        if str(e.get("label", "")) in _CODEABLE_LABELS
        and str(e.get("assertion", "present")).strip().lower() != "absent"
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

        if coded and score >= _CODING_SCORE_THRESHOLD:
            continue

        if _CODING_ALT_ENABLED and coded and score is not None and score >= _CODING_ALT_LOW:
            alt = _try_alt_coding(entity_text, entity_label)
            if alt:
                continue

        reviews.append(_build_review_item(label_id, idx, entity_text, entity_label, coded, top, score))

    return reviews


# ---------------------------------------------------------------------------
# Per-label processing (runs inside the outer ThreadPoolExecutor)
# ---------------------------------------------------------------------------

class _LabelResult:
    """Carries everything needed to write one label's outcome to Neo4j."""
    __slots__ = (
        "label_id", "updated_entities", "quality_score", "agreement",
        "n_disagreements", "review_items", "first_aws_label", "first_azure_label",
        "auto_resolved", "auto_resolve_method",
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
                    result.review_items.append({
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
                        "auto_resolve_confidence": _safe_float(triage.get("confidence")),
                        "auto_resolve_reason": str(triage.get("reason", ""))[:500],
                    })
                    continue

                result.review_items.append({
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
                })

        # Optionally append high-confidence "missing" spans proposed by either model.
        new_candidates: list[dict[str, Any]] = []
        for row in aws_rows + azure_rows:
            if not isinstance(row, dict):
                continue
            if not bool(row.get("is_new")):
                continue
            new_text = str(row.get("new_text") or row.get("text") or "").strip()
            suggested = _normalise_label(str(row.get("suggested_label", "finding")), "finding")
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
        _clean_observable_spans(text, updated_entities)
        _normalise_entity_types(updated_entities)
        _link_observable_value_units(updated_entities)
        apply_context_detection(text, updated_entities)

        result.coding_reviews = _check_terminology_coding(label_id, updated_entities, ignore_texts)

        total_entities = max(len(entities), 1)
        result.updated_entities = updated_entities
        result.n_disagreements = n_disagreements
        result.quality_score = max(0.0, min(1.0, (total_entities - n_disagreements) / total_entities))
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
# Main verification entry point
# ---------------------------------------------------------------------------

def run_verification() -> None:
    """Run full label verification job with parallel LLM calls.

    Phase 1 — Fetch all included TrainingLabel rows from Neo4j (one read session).
    Phase 2 — Process all labels concurrently via _MAX_WORKERS threads, each
               calling AWS + Azure in a nested 2-thread pool.
    Phase 3 — Write results back to Neo4j sequentially as futures complete
               (avoids multi-threaded session usage).
    """
    # ------------------------------------------------------------------
    # Phase 1: fetch
    # ------------------------------------------------------------------
    state = get_job_state()
    run_mode = str(state.get("run_mode") or "all")

    fetch_client = PatientGraphClient()
    try:
        with fetch_client.session() as session:
            rules = parse_rules([dict(r) for r in session.run(GET_ACTIVE_POST_PROCESSOR_RULES)])
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
                reviewed_ids = {str(r["label_id"]) for r in reviewed if r.get("label_id")}
                labels = [row for row in labels if str(row.get("label_id", "")) in reviewed_ids]
            elif run_mode == "resume":
                before = len(labels)
                labels = [
                    row for row in labels
                    if not row.get("verified_at")
                ]
                skipped = before - len(labels)
                logger.info("Resume mode: skipping %d already-verified labels", skipped)
    finally:
        fetch_client.close()

    _patch_state(total=len(labels))
    logger.info(
        "Label verification started: %d labels, max_workers=%d (~%d concurrent LLM requests)",
        len(labels), _MAX_WORKERS, _MAX_WORKERS * 2,
    )

    # ------------------------------------------------------------------
    # Phase 2 + 3: process in parallel, write sequentially as futures land
    # ------------------------------------------------------------------
    write_client = PatientGraphClient()
    try:
        with write_client.session() as session:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=_MAX_WORKERS,
                thread_name_prefix="label-verify",
            ) as pool:
                futures = {pool.submit(_process_label, row, rules, ignore_texts): row for row in labels}
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

                    # Write disagreement review items
                    for item in result.review_items:
                        session.run(
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
                            session.run(
                                RESOLVE_LABEL_VERIFICATION_REVIEW,
                                review_id=item["review_id"],
                                resolved_label=resolved_label,
                                reviewer=f"auto_triage:{item.get('auto_resolve_method', 'unknown')}",
                                entities_json=json.dumps(result.updated_entities),
                                model_a_was_correct=(item["model_a_label"] == resolved_label),
                                model_b_was_correct=(item["model_b_label"] == resolved_label),
                            )

                    # Write coding review items (uncoded / low-confidence entities)
                    for cr in result.coding_reviews:
                        session.run(
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
                        )

                    session.run(
                        UPDATE_TRAINING_LABEL_ENTITIES,
                        label_id=result.label_id,
                        entities_json=json.dumps(result.updated_entities),
                    )
                    session.run(
                        UPDATE_LABEL_VERIFICATION,
                        label_id=result.label_id,
                        verification_agreement=result.agreement,
                        model_a_label=result.first_aws_label,
                        model_b_label=result.first_azure_label,
                        quality_score=result.quality_score,
                    )

                    _increment_state(
                        done=1,
                        agreements=(1 if result.agreement else 0),
                        disagreements=result.n_disagreements,
                        auto_resolved=result.auto_resolved,
                        pending_review=sum(1 for item in result.review_items if not item.get("auto_resolved")),
                    )
                    state_now = get_job_state()
                    done_now = int(state_now.get("done") or 0)
                    total_now = int(state_now.get("total") or 0)
                    log_step = 25 if total_now <= 1000 else 100
                    if done_now >= total_now or done_now - last_progress_log_done >= log_step:
                        eta_seconds = state_now.get("eta_seconds")
                        eta_str = f"{eta_seconds}s" if isinstance(eta_seconds, int) else "unknown"
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

        _patch_state(status=("cancelled" if _stop_requested() else "done"), finished_at=time.time())
        logger.info("Label verification completed")

    except Exception as exc:
        logger.exception("Label verification failed")
        _patch_state(status="failed", finished_at=time.time(), last_error=str(exc))
    finally:
        write_client.close()
