"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-A23404E0
  DI: DI-23822663, DO-671C15BF
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A23404E0")
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_TNM_TRIPLET_RE = re.compile(
    r"\b(?:[cpyr]?t[0-4](?:[a-c])?)\s*(?:[cpyr]?n[0-3](?:[a-c])?)\s*"
    r"(?:[cpyr]?m[0-1](?:[a-c])?)\b",
    re.IGNORECASE,
)
_TNM_COMPONENT_RE = re.compile(r"[cpyr]?[tnm][0-4](?:[a-c])?", re.IGNORECASE)


@dataclass(frozen=True)
class TNMComponents:
    t: str
    n: str
    m: str
    prefix: str = ""
    raw: str = ""


def _normalise_component(value: str) -> tuple[str, str]:
    token = value.strip().upper()
    prefix = token[0] if token and token[0] in {"C", "P", "Y", "R"} else ""
    core = token[1:] if prefix else token
    return core, prefix


def parse_tnm_triplet(value: str) -> TNMComponents | None:
    """Parse TNM triplet text into structured components.

    Accepts formats like:
    - T2N1M0
    - pT3bN0M0
    - cT4a N1 M1
    """
    if not value:
        return None
    if not _TNM_TRIPLET_RE.search(value):
        return None
    parts = [m.group(0) for m in _TNM_COMPONENT_RE.finditer(value)]
    if len(parts) < 3:
        return None

    t_core, t_prefix = _normalise_component(parts[0])
    n_core, n_prefix = _normalise_component(parts[1])
    m_core, m_prefix = _normalise_component(parts[2])
    prefix = t_prefix or n_prefix or m_prefix
    return TNMComponents(t=t_core, n=n_core, m=m_core, prefix=prefix, raw=value.strip())
