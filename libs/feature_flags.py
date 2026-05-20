"""Lightweight feature-flag plumbing for staged rollouts.

Atlas trace:
  DI: DI-8A5FCF4F (Defence-in-depth episode detector with coverage fail-safe)
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-8A5FCF4F")

A flag value is resolved in this order, first hit wins:
  1. Explicit per-tenant override passed at call time.
  2. Per-tenant env var: <FLAG_NAME>__<TENANT_ID> (uppercased,
     non-alphanumerics replaced by underscore).
  3. Global env var: <FLAG_NAME>.
  4. Registered default.

Flag values are normalised to lowercase strings and matched against the
flag's allowed values before being returned. Unknown values fall back
to the registered default and emit a warning.

This module deliberately has no external dependencies so it is safe
to import from any worker, CLI, or test harness.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeatureFlag:
    """Immutable description of a feature flag."""

    name: str
    default: str
    allowed: tuple[str, ...]
    description: str

    def __post_init__(self) -> None:
        if self.default not in self.allowed:
            raise ValueError(
                f"FeatureFlag {self.name!r}: default {self.default!r} "
                f"not in allowed values {self.allowed!r}"
            )


_REGISTRY: dict[str, FeatureFlag] = {}
_OVERRIDES: dict[str, str] = {}
_LOCK = threading.Lock()


def register_flag(flag: FeatureFlag) -> FeatureFlag:
    """Register a flag and return it. Idempotent for identical re-registration."""
    with _LOCK:
        existing = _REGISTRY.get(flag.name)
        if existing is not None and existing != flag:
            raise ValueError(
                f"FeatureFlag {flag.name!r} already registered with different config"
            )
        _REGISTRY[flag.name] = flag
    return flag


def _tenant_key(name: str, tenant_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "_", tenant_id).strip("_").upper()
    return f"{name.upper()}__{safe}"


def resolve(flag_name: str, tenant_id: str | None = None) -> str:
    """Resolve the active value of a registered flag for a tenant."""
    flag = _REGISTRY.get(flag_name)
    if flag is None:
        raise KeyError(f"FeatureFlag {flag_name!r} is not registered")

    candidates: list[tuple[str, str | None]] = []

    process_override = _OVERRIDES.get(flag_name)
    if process_override is not None:
        candidates.append(("process_override", process_override))

    if tenant_id:
        env_key = _tenant_key(flag.name, tenant_id)
        candidates.append((env_key, os.environ.get(env_key)))

    candidates.append((flag.name.upper(), os.environ.get(flag.name.upper())))

    for source, raw in candidates:
        if raw is None:
            continue
        value = raw.strip().lower()
        if value in flag.allowed:
            return value
        logger.warning(
            "feature_flag %s: ignoring %s value %r (not in %r)",
            flag.name,
            source,
            raw,
            flag.allowed,
        )

    return flag.default


def set_process_override(flag_name: str, value: str) -> None:
    """Set an in-process override (used by tests)."""
    flag = _REGISTRY.get(flag_name)
    if flag is None:
        raise KeyError(f"FeatureFlag {flag_name!r} is not registered")
    if value not in flag.allowed:
        raise ValueError(f"value {value!r} not in {flag.allowed!r}")
    with _LOCK:
        _OVERRIDES[flag_name] = value


def clear_process_override(flag_name: str) -> None:
    """Remove a previously-set in-process override."""
    with _LOCK:
        _OVERRIDES.pop(flag_name, None)


def registered_flags() -> dict[str, FeatureFlag]:
    """Return a copy of the flag registry (for diagnostics)."""
    with _LOCK:
        return dict(_REGISTRY)


# -- Registered flags ---------------------------------------------------

EPISODE_PIPELINE = register_flag(
    FeatureFlag(
        name="episode_pipeline",
        default="v1",
        allowed=("v1", "v2", "shadow"),
        description=(
            "Selects which episode-detection pipeline runs. "
            "v1: legacy (episode_builder + episode_engine). "
            "v2: Episode Detector v2 (defence-in-depth, breast-only auto in v1). "
            "shadow: v1 publishes, v2 runs alongside writing to "
            "EpisodeShadowRun audit nodes for comparison."
        ),
    )
)


EXTRACTION_MODEL_MODE = register_flag(
    FeatureFlag(
        name="extraction_model_mode",
        default="llm",
        allowed=("llm", "ner", "auto"),
        description=(
            "Selects which extractor the extraction subgraph runs when the "
            "action does not pin a method. "
            "llm: always use the LLM extractor (current production default). "
            "ner: use the trained NER model; raises if the backend is "
            "unavailable when strict_model_version is set, otherwise falls "
            "back to LLM. "
            "auto: prefer NER when MODEL_MODE_NER_ENABLED is true and the "
            "backend is available; fall back to LLM on 0 entities or any "
            "NER error. Per-request override via the model_mode state key "
            "(propagated through pub/sub payload context.model_mode)."
        ),
    )
)


NCDA_DETECTOR = register_flag(
    FeatureFlag(
        name="ncda_detector",
        default="off",
        allowed=("off", "shadow", "on"),
        description=(
            "Routes cancer-suspect patients to the NCDA four-anchor detector. "
            "off: episode_detector_v2 runs unchanged. "
            "shadow: v2 publishes, NCDA detector runs alongside and writes "
            "evidence to NCDALabelAudit / NCDARunShadow for comparison. "
            "on: cancer-suspect patients route to the NCDA detector; everyone "
            "else stays on episode_detector_v2."
        ),
    )
)


# Patients qualify as cancer-suspect when at least one encounter scores
# >= this probability for FTR or Dx in the role classifier (Stage 13 plan).
NCDA_SUSPECT_PROBABILITY: float = 0.5


def is_cancer_suspect(role_scores: list[dict]) -> bool:
    """Return True when any encounter has FTR or Dx role probability >= 0.5.

    Stage 13 contract from the plan: "Cancer-suspect = patient with at least
    one role-classifier hit at P >= 0.5 for FTR or Dx".

    role_scores is an iterable of dicts shaped like::

        {"role": "ftr", "role_p": 0.83, ...}
    """
    for row in role_scores or []:
        if row.get("role") in {"ftr", "dx"} and float(
            row.get("role_p", 0.0)
        ) >= NCDA_SUSPECT_PROBABILITY:
            return True
    return False


def ncda_detector_should_run(
    role_scores: list[dict], tenant_id: str | None = None
) -> tuple[bool, str]:
    """Decide whether to invoke the NCDA detector for this patient.

    Returns ``(should_run, mode)`` where mode is the resolved flag value.
    The caller treats ``shadow`` as run-but-do-not-publish, and ``on`` as
    run-and-publish-when-cancer-suspect.
    """
    mode = resolve(NCDA_DETECTOR.name, tenant_id=tenant_id)
    if mode == "off":
        return False, mode
    if mode == "shadow":
        return True, mode
    return is_cancer_suspect(role_scores), mode
