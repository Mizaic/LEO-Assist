"""Map UK extraction concept IDs to LabResultConfig primary IDs.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Terminology resolve prefers UK observable entities (for example mass
concentration of haemoglobin in blood). Seeded lab metadata often uses
the international / legacy SNOMED IDs. Resolve aliases before lookup so
derived findings and guideline classification stay aligned.
"""

from __future__ import annotations

# Extracted / resolved concept_id -> LabResultConfig.conceptId
LAB_CONFIG_CONCEPT_ALIASES: dict[str, str] = {
    # Mass concentration of haemoglobin in blood -> Haemoglobin
    "1107511000000100": "365616006",
    # Registry haemoglobin (WHO-style) -> haematology defaults haemoglobin
    "271026005": "365616006",
    # Serum amylase level -> Amylase
    "997491000000108": "104187009",
}


def resolve_lab_config_concept_id(concept_id: str) -> str:
    """Return the LabResultConfig concept id for an extracted observable."""
    key = str(concept_id or "").strip()
    if not key:
        return key
    return LAB_CONFIG_CONCEPT_ALIASES.get(key, key)
