"""Per-site episode rulebook artefacts and runtime loader.

Atlas trace:
  UN: UN-B0A58F43 (Portable per-site episode rulebooks)
  DIs: DI-951F26E0 (schema+validator),
       DI-FA3CE229 (loader+bundle),
       DI-BF97CEAC (registry),
       DI-AC6838DD (promotion gate),
       DI-D983C6EE (retrain)
  Risks mitigated: R-94D0D086 (drift), R-192A2D18 (PII leakage),
                   R-5FA0C950 (cross-site leakage), R-098701D8 (skew)

The rulebook artefact is the portable, versioned, per-site knowledge
the detector uses. One JSON file per site. No patient data, ever.
See compliance/atlas-migration-evidence/rulebook-atlas-ids.md.
"""

from libs.episode_detector.rulebook import (
    RulebookBundle,
    RulebookPiiError,
    RulebookSchemaVersionError,
    SiteRulebook,
    SUPPORTED_SCHEMA_RANGE,
    validate_no_pii,
)

__all__ = [
    "RulebookBundle",
    "RulebookPiiError",
    "RulebookSchemaVersionError",
    "SUPPORTED_SCHEMA_RANGE",
    "SiteRulebook",
    "validate_no_pii",
]
