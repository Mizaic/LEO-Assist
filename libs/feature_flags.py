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
