"""Fast bitmap-based guideline evaluation against patient SNOMED codes.

Evaluation logic:
  A rule MATCHES when ALL of its criteria_groups pass AND all APPLIES_TO
  demographic constraints are satisfied.

  Per-group semantics:
    mode="ALL"  — every concept in the group bitmap IS in the patient set
                  (bitmap is a subset of the patient bitmap)
    mode="ANY"  — at least one concept in the group bitmap IS in the patient set
                  (bitmap intersection with patient bitmap is non-empty)
    mode="NOT"  — NO concept in the group bitmap IS in the patient set
                  (bitmap intersection with patient bitmap is empty)

Evaluation is deterministic, auditable, and typically completes in
microseconds for rulesets of up to 500 rules.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

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
        patient_age: float | None = None,
        patient_sex: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate patient SNOMED codes against the active bitmap ruleset.

        Args:
            patient_codes: List of SNOMED concept ID strings for the patient.
            pathway_filter: Optional guideline ID to restrict evaluation to one
                            guideline (e.g. ``NG151``).
            patient_age: Patient age in years (decimal).  Required for rules
                         with age-based ``APPLIES_TO`` constraints.
            patient_sex: ``"female"`` or ``"male"``.  If provided and the
                         patient sex code (248152002 / 248153007) is not already
                         in ``patient_codes``, it is injected automatically.

        Returns:
            Dict with ``matched_rules`` list and ``active_version`` string.
        """
        ruleset = self._store.get_current_ruleset()
        if not ruleset:
            logger.warning(
                "GuidelineEvaluator: no active ruleset found in Redis — "
                "ALL patient evaluations will return zero matches. "
                "Run POST /compile to rebuild the ruleset."
            )
            return {
                "matched_rules": [],
                "active_version": None,
                "message": "No active ruleset compiled yet.",
            }

        # Inject sex SNOMED concept if caller supplies it as a string
        effective_codes = list(patient_codes)
        if patient_sex:
            sex_code = _SEX_CODE.get(patient_sex.lower().strip())
            if sex_code and sex_code not in effective_codes:
                effective_codes.append(sex_code)

        patient_bitmap = self._build_patient_bitmap(effective_codes)
        rules = ruleset.get("rules", [])
        matches = []

        for rule in rules:
            if pathway_filter and rule.get("guideline_id") != pathway_filter:
                continue
            if self._rule_matches(rule, patient_bitmap, patient_age, patient_sex):
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

    def _rule_matches(
        self,
        rule: dict,
        patient_bm: BitMap,
        patient_age: float | None = None,
        patient_sex: str | None = None,
    ) -> bool:
        """Return True if a compiled rule matches the patient bitmap.

        Evaluation order:
        1. ``APPLIES_TO`` demographic constraints (age) — any unmet constraint
           immediately disqualifies the rule.
        2. ``criteria_groups`` — each group is evaluated by its mode (ALL/ANY/NOT).
           ALL groups must pass (AND between groups).

        A rule with no groups and no applies_to cannot match any patient and
        returns False.

        Args:
            rule: Compiled rule dict from the ruleset.
            patient_bm: Patient BitMap built from their SNOMED codes.
            patient_age: Patient age in decimal years for age constraint checks.

        Returns:
            True if the patient satisfies all criteria.
        """
        if int(rule.get("schema_version") or 1) == 2:
            logic_tree = rule.get("logic_tree")
            if not logic_tree:
                return False
            return self._logic_tree_matches(logic_tree, patient_bm, patient_age, patient_sex)

        applies_to = rule.get("applies_to") or []
        if applies_to and not _check_applies_to(applies_to, patient_age):
            return False

        criteria_groups = rule.get("criteria_groups") or []
        if not criteria_groups:
            # A rule with only applies_to constraints (no bitmap groups) fires when
            # the demographic gate passes — only if applies_to is non-empty.
            return bool(applies_to)

        any_group_evaluated = False
        for group in criteria_groups:
            bitmap_id = group.get("bitmap_id")
            if not bitmap_id:
                continue
            mode = str(group.get("mode", "ALL")).upper()
            bm = self._store.get_bitmap(bitmap_id)
            if bm is None:
                # A missing bitmap means Redis data is corrupt or was evicted.
                # We CANNOT safely evaluate this group in any mode:
                #   ALL missing → cannot confirm required criteria are met
                #   ANY missing → cannot confirm at least one criterion is met
                #   NOT missing → cannot confirm exclusion criteria are absent
                # In all cases, fail CLOSED (do not fire the rule).
                logger.error(
                    "Bitmap %r for mode=%s group of rule %r is MISSING from Redis — "
                    "failing CLOSED: rule will NOT fire for this patient. "
                    "Redis data may be corrupt or evicted. Run POST /compile to rebuild.",
                    bitmap_id, mode, rule.get("rule_id"),
                )
                return False
            any_group_evaluated = True

            if mode == "ALL":
                if not bm.issubset(patient_bm):
                    return False
            elif mode == "ANY":
                if len(bm & patient_bm) == 0:
                    return False
            elif mode == "NOT":
                if len(bm & patient_bm) > 0:
                    return False

        return any_group_evaluated or bool(applies_to)

    def _logic_tree_matches(
        self,
        node: dict[str, Any] | None,
        patient_bm: BitMap,
        patient_age: float | None,
        patient_sex: str | None,
    ) -> bool:
        if not node:
            return False
        kind = str(node.get("kind") or "").upper()
        if kind == "CONCEPT":
            bitmap_id = node.get("bitmap_id")
            bm = self._store.get_bitmap(bitmap_id) if bitmap_id else None
            if bm is None:
                logger.error(
                    "Schema v2 bitmap %r for rule node %r is missing from Redis — failing CLOSED.",
                    bitmap_id,
                    node.get("node_id"),
                )
                return False
            return len(bm & patient_bm) > 0
        if kind == "DEMOGRAPHIC":
            return _check_demographic_node(node, patient_age, patient_sex)
        children = list(node.get("children") or [])
        if kind == "AND":
            return all(self._logic_tree_matches(child, patient_bm, patient_age, patient_sex) for child in children)
        if kind == "OR":
            return any(self._logic_tree_matches(child, patient_bm, patient_age, patient_sex) for child in children)
        if kind == "NOT":
            if len(children) != 1:
                logger.error("Schema v2 NOT node %r must contain exactly one child.", node.get("node_id"))
                return False
            return not self._logic_tree_matches(children[0], patient_bm, patient_age, patient_sex)
        if kind == "AT_LEAST":
            threshold = int(node.get("min") or 1)
            count = sum(
                1 for child in children
                if self._logic_tree_matches(child, patient_bm, patient_age, patient_sex)
            )
            return count >= threshold
        logger.error("Unknown schema v2 logic node kind %r — failing CLOSED.", kind)
        return False


# Maps caller-supplied sex string to the SNOMED concept ID injected into
# the patient bitmap so sex-based HAS_CRITERIA rules fire automatically.
_SEX_CODE: dict[str, str] = {
    "female": "248152002",
    "f":      "248152002",
    "male":   "248153007",
    "m":      "248153007",
}

# SNOMED age observable concept — used to identify age constraints in applies_to
_AGE_CONCEPT_ID = "424144002"

_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    ">=": lambda a, v: a >= v,
    ">":  lambda a, v: a > v,
    "<=": lambda a, v: a <= v,
    "<":  lambda a, v: a < v,
    "=":  lambda a, v: a == v,
}


def _check_applies_to(
    constraints: list[dict],
    patient_age: float | None,
) -> bool:
    """Return True only when every APPLIES_TO constraint is satisfied.

    Currently supports age constraints (concept 424144002).

    SAFETY: Unknown concept types FAIL CLOSED (return False) rather than
    being silently skipped.  This prevents rules from firing for patients
    who should be excluded by an unrecognised demographic gate.  Add
    explicit handling below before adding new APPLIES_TO concept types
    to Neo4j.

    Args:
        constraints: List of constraint dicts from the compiled rule.
        patient_age: Patient age in decimal years, or None if unknown.

    Returns:
        False if any constraint fails, cannot be evaluated, or is unrecognised.
    """
    for c in constraints:
        concept_id = c.get("concept_id")
        operator = c.get("operator")
        value = c.get("value")

        if concept_id == _AGE_CONCEPT_ID:
            if patient_age is None:
                logger.warning(
                    "Age constraint (%s %s years) cannot be evaluated — "
                    "patient_age not supplied; failing CLOSED (rule will not fire).",
                    operator, value,
                )
                return False
            op_fn = _OPERATORS.get(operator or ">=")
            if op_fn is None or value is None:
                logger.error(
                    "Unrecognised age constraint operator %r (value=%r) — "
                    "failing CLOSED: rule will not fire.",
                    operator, value,
                )
                return False
            if not op_fn(patient_age, value):
                return False
        else:
            # FAIL CLOSED — do not silently skip unrecognised constraint types.
            # If this is logged in production, add a handler for concept_id above.
            logger.error(
                "APPLIES_TO constraint has unrecognised concept_id %r "
                "(operator=%r, value=%r) — failing CLOSED: rule will NOT fire "
                "for any patient until this constraint type is implemented. "
                "Add handling for concept %r in _check_applies_to.",
                concept_id, operator, value, concept_id,
            )
            return False

    return True


def _check_demographic_node(
    node: dict[str, Any],
    patient_age: float | None,
    patient_sex: str | None,
) -> bool:
    field = str(node.get("field") or "").lower()
    operator = str(node.get("operator") or "=")
    value = node.get("value")
    if field == "age":
        if patient_age is None:
            logger.warning(
                "Age logic node (%s %s %s) cannot be evaluated — patient_age not supplied; failing CLOSED.",
                operator,
                value,
                node.get("unit"),
            )
            return False
        op_fn = _OPERATORS.get(operator)
        if op_fn is None or value is None:
            logger.error("Invalid age logic node operator/value (%r, %r) — failing CLOSED.", operator, value)
            return False
        return op_fn(patient_age, float(value))
    if field == "sex":
        if not patient_sex:
            logger.warning("Sex logic node cannot be evaluated — patient_sex not supplied; failing CLOSED.")
            return False
        if operator != "=":
            logger.error("Unsupported sex logic node operator %r — failing CLOSED.", operator)
            return False
        return patient_sex.lower().strip() == str(value or "").lower().strip()
    logger.error("Unknown demographic field %r — failing CLOSED.", field)
    return False


def _format_match(rule: dict) -> dict:
    """Format a matched rule for the API response.

    Args:
        rule: Compiled rule dict from the ruleset.

    Returns:
        Response dict with rule metadata and ``action`` sub-dict when a
        SNOMED procedure was coded for the rule.  ``action.priority`` is one of
        ``"2ww"`` | ``"urgent"`` | ``"routine"``.  ``action.due_days`` is the
        maximum calendar days allowed (14 for 2WW, 2 for urgent 48h, etc.)
        or ``null`` for routine actions.
    """
    return {
        "rule_id":                 rule["rule_id"],
        "name":                    rule.get("name"),
        "strength":                rule.get("strength"),
        "guideline_id":            rule.get("guideline_id"),
        "guideline_title":         rule.get("guideline_title"),
        "chapter_title":           rule.get("chapter_title"),
        "recommendation_verbatim": rule.get("recommendation_verbatim"),
        "action":                  rule.get("action"),
        "confidence":              1.0,
    }
