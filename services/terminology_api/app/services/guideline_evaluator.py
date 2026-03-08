"""Fast bitmap-based guideline evaluation against patient SNOMED codes.

Evaluation logic:
  A rule MATCHES when:
    - Every PRESENT concept in the rule IS in the patient's code set
      (req_all bitmap fully intersects patient bitmap), AND
    - No ABSENT concept in the rule IS in the patient's code set
      (forbid bitmap does NOT intersect patient bitmap)

Evaluation is deterministic, auditable, and typically completes in
microseconds for rulesets of up to 500 rules.
"""

from __future__ import annotations

import logging
from typing import Any

from pyroaring import BitMap

from services.terminology_api.app.services.bitmap_store import BitmapStore

logger = logging.getLogger(__name__)


class GuidelineEvaluator:
    """Evaluates a patient's SNOMED code set against the active ruleset.

    Loads the active ruleset from Redis on each call. The ruleset is small
    (typically a few KB of JSON) and Redis is local or low-latency, so the
    load overhead is negligible.
    """

    def __init__(self, store: BitmapStore | None = None) -> None:
        self._store = store or BitmapStore()

    def evaluate_patient(
        self,
        patient_codes: list[str],
        pathway_filter: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate patient SNOMED codes against the active bitmap ruleset.

        Args:
            patient_codes: List of SNOMED concept ID strings for the patient.
            pathway_filter: Optional guideline ID to restrict evaluation to one
                            guideline (e.g. ``NG151``).

        Returns:
            Dict with ``matched_rules`` list and ``active_version`` string.
        """
        ruleset = self._store.get_current_ruleset()
        if not ruleset:
            return {
                "matched_rules": [],
                "active_version": None,
                "message": "No active ruleset compiled yet.",
            }

        patient_bitmap = self._build_patient_bitmap(patient_codes)
        rules = ruleset.get("rules", [])
        matches = []

        for rule in rules:
            if pathway_filter and rule.get("guideline_id") != pathway_filter:
                continue
            if self._rule_matches(rule, patient_bitmap):
                matches.append(_format_match(rule))

        return {
            "matched_rules": matches,
            "active_version": ruleset.get("version"),
            "compile_timestamp": ruleset.get("compile_timestamp"),
        }

    def _build_patient_bitmap(self, concept_ids: list[str]) -> BitMap:
        """Map patient concept IDs to integer IDs and build a BitMap.

        Concept IDs not yet in the store are silently skipped --
        unknown codes cannot match any rule.

        Args:
            concept_ids: Patient SNOMED concept ID strings.

        Returns:
            PyRoaring BitMap containing mapped integer IDs.
        """
        int_ids = []
        for cid in concept_ids:
            iid = self._store.get_int_id(cid)
            if iid is not None:
                int_ids.append(iid)
        return BitMap(int_ids)

    def _rule_matches(self, rule: dict, patient_bm: BitMap) -> bool:
        """Return True if a compiled rule matches the patient bitmap.

        Args:
            rule: Compiled rule dict from the ruleset.
            patient_bm: Patient BitMap built from their SNOMED codes.

        Returns:
            True if the patient satisfies all required criteria and has
            no excluded criteria.
        """
        req_id = rule.get("req_all_bitmap_id")
        if req_id:
            req_bm = self._store.get_bitmap(req_id)
            if req_bm is None:
                return False
            if not req_bm.issubset(patient_bm):
                return False

        forbid_id = rule.get("forbid_bitmap_id")
        if forbid_id:
            forbid_bm = self._store.get_bitmap(forbid_id)
            if forbid_bm and len(forbid_bm & patient_bm) > 0:
                return False

        return req_id is not None


def _format_match(rule: dict) -> dict:
    """Format a matched rule for the API response.

    Args:
        rule: Compiled rule dict from the ruleset.

    Returns:
        Response dict with rule metadata.
    """
    return {
        "rule_id": rule["rule_id"],
        "name": rule.get("name"),
        "strength": rule.get("strength"),
        "guideline_id": rule.get("guideline_id"),
        "guideline_title": rule.get("guideline_title"),
        "recommendation_verbatim": rule.get("recommendation_verbatim"),
        "confidence": 1.0,
    }
