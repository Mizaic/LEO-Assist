"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-4D608335
  DI: DI-760F5FB7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-4D608335")

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
UKCR_DIR_PREFIX = "SnomedCT_UKClinicalRefsetsRF2_PRODUCTION_"


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
    if not base.exists():
        logger.warning("SNOMED base directory not found: %s", base)
        return None
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

    def uked_concept(self) -> Path | None:
        d = self._snap_term(UKED_DIR_PREFIX)
        return _find_one(d, "sct2_Concept_UKEDSnapshot_*.txt") if d else None

    def uked_description(self) -> Path | None:
        d = self._snap_term(UKED_DIR_PREFIX)
        return _find_one(d, "sct2_Description_UKEDSnapshot-en_*.txt") if d else None

    def uked_relationship(self) -> Path | None:
        d = self._snap_term(UKED_DIR_PREFIX)
        return _find_one(d, "sct2_Relationship_UKEDSnapshot_*.txt") if d else None

    def uked_simple_map(self) -> Path | None:
        d = self._snap_refset_map(UKED_DIR_PREFIX)
        return _find_one(d, "der2_sRefset_SimpleMapUKEDSnapshot_*.txt") if d else None

    def uked_extended_map(self) -> Path | None:
        d = self._snap_refset_map(UKED_DIR_PREFIX)
        return (
            _find_one(d, "der2_iisssciRefset_ExtendedMapUKEDSnapshot_*.txt")
            if d
            else None
        )

    def ukcr_concept(self) -> Path | None:
        d = self._snap_term(UKCR_DIR_PREFIX)
        return _find_one(d, "sct2_Concept_UKCRSnapshot_*.txt") if d else None

    def ukcr_description(self) -> Path | None:
        d = self._snap_term(UKCR_DIR_PREFIX)
        return _find_one(d, "sct2_Description_UKCRSnapshot-en_*.txt") if d else None

    def ukcr_relationship(self) -> Path | None:
        d = self._snap_term(UKCR_DIR_PREFIX)
        return _find_one(d, "sct2_Relationship_UKCRSnapshot_*.txt") if d else None

    def ukcr_language(self) -> Path | None:
        d = self._snap_refset_lang(UKCR_DIR_PREFIX)
        return _find_one(d, "der2_cRefset_LanguageUKCRSnapshot-en_*.txt") if d else None

    def ukcr_simple_map(self) -> Path | None:
        d = self._snap_refset_map(UKCR_DIR_PREFIX)
        return _find_one(d, "der2_sRefset_SimpleMapUKCRSnapshot_*.txt") if d else None

    def ukcr_extended_map(self) -> Path | None:
        d = self._snap_refset_map(UKCR_DIR_PREFIX)
        return (
            _find_one(d, "der2_iisssciRefset_ExtendedMapUKCRSnapshot_*.txt")
            if d
            else None
        )

    def int_extended_map(self) -> Path | None:
        d = self._snap_refset_map(INT_DIR_PREFIX)
        return (
            _find_one(d, "der2_iisssccRefset_ExtendedMapSnapshot_INT_*.txt")
            if d
            else None
        )

    def ukcl_extended_map(self) -> Path | None:
        d = self._snap_refset_map(UKCL_DIR_PREFIX)
        return (
            _find_one(d, "der2_iisssciRefset_ExtendedMapUKCLSnapshot_*.txt")
            if d
            else None
        )

    def int_simple_map(self) -> Path | None:
        d = self._snap_refset_map(INT_DIR_PREFIX)
        return _find_one(d, "der2_sRefset_SimpleMapSnapshot_INT_*.txt") if d else None

    def all_found(self) -> dict[str, Path | None]:
        return {
            "int_concept": self.int_concept(),
            "ukcl_concept": self.ukcl_concept(),
            "uked_concept": self.uked_concept(),
            "ukcr_concept": self.ukcr_concept(),
            "int_description": self.int_description(),
            "ukcl_description": self.ukcl_description(),
            "uked_description": self.uked_description(),
            "ukcr_description": self.ukcr_description(),
            "int_relationship": self.int_relationship(),
            "ukcl_relationship": self.ukcl_relationship(),
            "uked_relationship": self.uked_relationship(),
            "ukcr_relationship": self.ukcr_relationship(),
            "ukcl_language": self.ukcl_language(),
            "uked_language": self.uked_language(),
            "ukcr_language": self.ukcr_language(),
            "int_extended_map": self.int_extended_map(),
            "ukcl_extended_map": self.ukcl_extended_map(),
            "uked_extended_map": self.uked_extended_map(),
            "ukcr_extended_map": self.ukcr_extended_map(),
            "int_simple_map": self.int_simple_map(),
            "uked_simple_map": self.uked_simple_map(),
            "ukcr_simple_map": self.ukcr_simple_map(),
        }


class DmdFiles:
    """Resolves paths for dm+d drug extension XML files."""

    def __init__(self, external_content: Path):
        self._dir = external_content / "trud-snomed-ct-drug-extension"

    def dmd_dir(self) -> Path | None:
        return self._dir if self._dir.exists() else None

    def all_found(self) -> dict[str, Path | None]:
        return {"dmd_dir": self.dmd_dir()}


ICD10_BASE = "trud-nhs-icd10"
OPCS4_BASE = "trud-nhs-opcs4"


class Icd10Files:
    """Resolves the ClaML XML payload for the NHS ICD-10 5th Edition release."""

    def __init__(self, external_content: Path):
        self._dir = external_content / ICD10_BASE

    def icd10_xml(self) -> Path | None:
        if not self._dir.exists():
            logger.warning("ICD-10 base directory not found: %s", self._dir)
            return None
        candidates = [
            *self._dir.rglob("*ICD10*.xml"),
            *self._dir.rglob("*icd10*.xml"),
            *self._dir.rglob("*.xml"),
        ]
        seen: set[Path] = set()
        unique: list[Path] = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        if not unique:
            logger.warning("No ICD-10 XML found under %s", self._dir)
            return None
        return sorted(unique)[-1]

    def all_found(self) -> dict[str, Path | None]:
        return {"icd10_xml": self.icd10_xml()}


class Opcs4Files:
    """Resolves the codes-and-titles text file for the OPCS-4 release."""

    def __init__(self, external_content: Path):
        self._dir = external_content / OPCS4_BASE

    def opcs4_codes(self) -> Path | None:
        if not self._dir.exists():
            logger.warning("OPCS-4 base directory not found: %s", self._dir)
            return None
        candidates = [
            *self._dir.rglob("*CodesAndTitles*.txt"),
            *self._dir.rglob("*codes*titles*.txt"),
            *self._dir.rglob("OPCS*.txt"),
            *self._dir.rglob("*.txt"),
        ]
        seen: set[Path] = set()
        unique: list[Path] = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        if not unique:
            logger.warning("No OPCS-4 codes file found under %s", self._dir)
            return None
        return sorted(unique)[-1]

    def all_found(self) -> dict[str, Path | None]:
        return {"opcs4_codes": self.opcs4_codes()}
