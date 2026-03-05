"""Versioned prompt registry.

All LLM prompts live here so they can be versioned, tested, and shared
across the API pipeline, coding worker, and analysis worker.

Usage::

    from libs.prompts.registry import get_prompt

    system = get_prompt("extraction", version=1)
    system = get_prompt("disambiguation", version=1)
    system = get_prompt("episode_builder_system", version=1)
"""
from __future__ import annotations

from typing import Dict, Tuple

_REGISTRY: Dict[Tuple[str, int], str] = {}


def register(name: str, version: int, text: str) -> None:
    _REGISTRY[(name, version)] = text


def get_prompt(name: str, version: int = 1) -> str:
    """Return the prompt text for *name* at *version*.

    Raises ``KeyError`` if the combination is not registered.
    """
    key = (name, version)
    if key not in _REGISTRY:
        available = [k for k in _REGISTRY if k[0] == name]
        if available:
            versions = sorted(v for _, v in available)
            raise KeyError(
                f"Prompt {name!r} has no version {version}; "
                f"available versions: {versions}"
            )
        raise KeyError(
            f"Unknown prompt {name!r}. Registered: "
            f"{sorted(set(k[0] for k in _REGISTRY))}"
        )
    return _REGISTRY[key]


def list_prompts() -> list[tuple[str, int]]:
    """Return all registered (name, version) pairs."""
    return sorted(_REGISTRY.keys())


# Auto-register all bundled prompt modules on import.
from libs.prompts import extraction_v1 as _ext  # noqa: F401, E402
from libs.prompts import disambiguation_v1 as _dis  # noqa: F401, E402
from libs.prompts import episode_builder_v1 as _ep  # noqa: F401, E402
from libs.prompts import encounter_classify_v1 as _enc  # noqa: F401, E402
from libs.prompts import anchor_domain_review_v1 as _anc  # noqa: F401, E402
from libs.prompts import exclusion_detect_v1 as _excl  # noqa: F401, E402
from libs.prompts import label_verification_v2 as _lv2  # noqa: F401, E402
from libs.prompts import label_disambiguation_v1 as _ld1  # noqa: F401, E402
from libs.prompts import opus_audit_v1 as _oa1  # noqa: F401, E402
