"""Frozen 20-patient regression cohort for the Haiku episode engine.

The cohort is defined here as **synthetic ids only** (SYN-EE-001 ..
SYN-EE-020). Real NHS numbers are NEVER stored in source control or in
test definitions. They live in the gitignored secrets bundle:

    secrets/episode_engine_cohort_map.json

That file maps synthetic ids -> real Neo4j patient ids for runtime use
by the regeneration script and the gated frozen-cohort VT. The
committed regression baseline (baseline.json) is keyed by synthetic id
only.

If the secrets file is missing or incomplete, runtime helpers raise a
clear error; tests that depend on the real graph are skipped.

Synthetic id contract
---------------------
- SYN-EE-001 is reserved for the canonical breast-cancer reference
  case (the patient that motivated the rule -> LLM rewrite). Any
  documentation, prompt, or test that mentions a worked example
  refers to SYN-EE-001.
- SYN-EE-002 .. SYN-EE-010 are the rest of the spike cohort.
- SYN-EE-011 .. SYN-EE-020 are the additional high-encounter
  patients added when extending to 20.
- Do NOT renumber. Append-only.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

# -- Synthetic ids (the only ids ever committed to source control) -----------
SPIKE_COHORT: tuple[str, ...] = tuple(
    f"SYN-EE-{n:03d}" for n in range(1, 11)
)

EXTENDED_COHORT: tuple[str, ...] = tuple(
    f"SYN-EE-{n:03d}" for n in range(11, 21)
)

FROZEN_COHORT: tuple[str, ...] = SPIKE_COHORT + EXTENDED_COHORT

assert len(set(FROZEN_COHORT)) == 20, "Frozen cohort must have 20 unique ids."


# -- Secrets-backed resolver (runtime only; never imported by tests directly)
_DEFAULT_MAP_PATH = (
    Path(__file__).resolve().parents[3]
    / "secrets"
    / "episode_engine_cohort_map.json"
)


class CohortMappingError(RuntimeError):
    """Raised when the synthetic -> real id mapping is missing or invalid."""


def _load_mapping(path: Path | None = None) -> Mapping[str, str]:
    """Load the synthetic -> real patient id mapping from secrets.

    The file is expected to contain a single JSON object, e.g.
    ``{"SYN-EE-001": "9990000001", ...}``. The function validates that
    every synthetic id in FROZEN_COHORT has a non-empty real id.
    """

    map_path = path or Path(
        os.environ.get(
            "EPISODE_ENGINE_COHORT_MAP",
            str(_DEFAULT_MAP_PATH),
        )
    )
    if not map_path.exists():
        raise CohortMappingError(
            "Cohort mapping file not found at "
            f"{map_path}. Create it as JSON of the form "
            '{"SYN-EE-001": "<real-id>", ...} or set '
            "EPISODE_ENGINE_COHORT_MAP to a custom path."
        )

    raw = json.loads(map_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CohortMappingError(
            f"Cohort mapping at {map_path} must be a JSON object."
        )

    missing = [s for s in FROZEN_COHORT if not raw.get(s)]
    if missing:
        raise CohortMappingError(
            f"Cohort mapping at {map_path} is missing real ids for: "
            + ", ".join(missing)
        )
    return {sid: str(raw[sid]) for sid in FROZEN_COHORT}


def resolve_real_id(synthetic_id: str, path: Path | None = None) -> str:
    """Return the real Neo4j patient id for ``synthetic_id``.

    Raises CohortMappingError if the mapping is missing or the id is
    not in FROZEN_COHORT.
    """

    if synthetic_id not in FROZEN_COHORT:
        raise CohortMappingError(
            f"{synthetic_id} is not part of FROZEN_COHORT."
        )
    return _load_mapping(path)[synthetic_id]


def iter_resolved_pairs(
    path: Path | None = None,
) -> list[tuple[str, str]]:
    """Yield ``(synthetic_id, real_id)`` for every cohort patient."""

    mapping = _load_mapping(path)
    return [(sid, mapping[sid]) for sid in FROZEN_COHORT]
