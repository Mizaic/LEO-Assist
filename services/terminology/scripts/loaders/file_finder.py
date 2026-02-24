"""
Locate SNOMED RF2 and dm+d files within external_content/.

Handles the variable directory names (date-stamped) by globbing.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SNOMED_BASE = "trud-snomed-uk-clinical-edition"

INT_DIR_PREFIX = "SnomedCT_InternationalRF2_PRODUCTION_"
UKCL_DIR_PREFIX = "SnomedCT_UKClinicalRF2_PRODUCTION_"
UKED_DIR_PREFIX = "SnomedCT_UKEditionRF2_PRODUCTION_"


def _find_one(base: Path, pattern: str) -> Path | None:
    matches = sorted(base.glob(pattern))
    if not matches:
        logger.warning("No file matching %s in %s", pattern, base)
        return None
    result = matches[-1]
    logger.debug("Found: %s", result)
    return result


def _snomed_dir(external: Path, prefix: str) -> Path | None:
    base = external / SNOMED_BASE
    for d in sorted(base.iterdir()):
        if d.is_dir() and d.name.startswith(prefix):
            return d
    return None


class SnomedFiles:
    """Resolves paths for SNOMED RF2 Snapshot files."""

    def __init__(self, external_content: Path):
        self._ext = external_content

    def _snap_term(self, prefix: str) -> Path | None:
        d = _snomed_dir(self._ext, prefix)
        if not d:
            return None
        return d / "Snapshot" / "Terminology"

    def _snap_refset_map(self, prefix: str) -> Path | None:
        d = _snomed_dir(self._ext, prefix)
        if not d:
            return None
        return d / "Snapshot" / "Refset" / "Map"

    def _snap_refset_lang(self, prefix: str) -> Path | None:
        d = _snomed_dir(self._ext, prefix)
        if not d:
            return None
        return d / "Snapshot" / "Refset" / "Language"

    def int_concept(self) -> Path | None:
        d = self._snap_term(INT_DIR_PREFIX)
        return _find_one(d, "sct2_Concept_Snapshot_INT_*.txt") if d else None

    def ukcl_concept(self) -> Path | None:
        d = self._snap_term(UKCL_DIR_PREFIX)
        return _find_one(d, "sct2_Concept_UKCLSnapshot_*.txt") if d else None

    def int_description(self) -> Path | None:
        d = self._snap_term(INT_DIR_PREFIX)
        return _find_one(d, "sct2_Description_Snapshot-en_INT_*.txt") if d else None

    def ukcl_description(self) -> Path | None:
        d = self._snap_term(UKCL_DIR_PREFIX)
        return _find_one(d, "sct2_Description_UKCLSnapshot-en_*.txt") if d else None

    def int_relationship(self) -> Path | None:
        d = self._snap_term(INT_DIR_PREFIX)
        return _find_one(d, "sct2_Relationship_Snapshot_INT_*.txt") if d else None

    def ukcl_relationship(self) -> Path | None:
        d = self._snap_term(UKCL_DIR_PREFIX)
        return _find_one(d, "sct2_Relationship_UKCLSnapshot_*.txt") if d else None

    def ukcl_language(self) -> Path | None:
        d = self._snap_refset_lang(UKCL_DIR_PREFIX)
        return _find_one(d, "der2_cRefset_LanguageUKCLSnapshot-en_*.txt") if d else None

    def uked_language(self) -> Path | None:
        d = self._snap_refset_lang(UKED_DIR_PREFIX)
        return _find_one(d, "der2_cRefset_LanguageUKEDSnapshot-en_*.txt") if d else None

    def int_extended_map(self) -> Path | None:
        d = self._snap_refset_map(INT_DIR_PREFIX)
        return _find_one(d, "der2_iisssccRefset_ExtendedMapSnapshot_INT_*.txt") if d else None

    def ukcl_extended_map(self) -> Path | None:
        d = self._snap_refset_map(UKCL_DIR_PREFIX)
        return _find_one(d, "der2_iisssciRefset_ExtendedMapUKCLSnapshot_*.txt") if d else None

    def int_simple_map(self) -> Path | None:
        d = self._snap_refset_map(INT_DIR_PREFIX)
        return _find_one(d, "der2_sRefset_SimpleMapSnapshot_INT_*.txt") if d else None

    def all_found(self) -> dict[str, Path | None]:
        return {
            "int_concept": self.int_concept(),
            "ukcl_concept": self.ukcl_concept(),
            "int_description": self.int_description(),
            "ukcl_description": self.ukcl_description(),
            "int_relationship": self.int_relationship(),
            "ukcl_relationship": self.ukcl_relationship(),
            "ukcl_language": self.ukcl_language(),
            "uked_language": self.uked_language(),
            "int_extended_map": self.int_extended_map(),
            "ukcl_extended_map": self.ukcl_extended_map(),
            "int_simple_map": self.int_simple_map(),
        }


class DmdFiles:
    """Resolves paths for dm+d drug extension XML files."""

    def __init__(self, external_content: Path):
        self._dir = external_content / "trud-snomed-ct-drug-extension"

    def dmd_dir(self) -> Path | None:
        return self._dir if self._dir.exists() else None

    def all_found(self) -> dict[str, Path | None]:
        return {"dmd_dir": self.dmd_dir()}
