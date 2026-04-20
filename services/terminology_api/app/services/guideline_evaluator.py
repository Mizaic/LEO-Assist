"""Fast bitmap-based guideline evaluation against patient SNOMED codes.

Atlas trace:
  DO: DO-E74B0605
  DI: DI-5E25E872
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-E74B0605")

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


def _rule_stem(rule_id: str | None) -> str:
    """Return the canonical rule identity, stripping any ``:edit:*`` chain.

    Mirrors :func:`services.api.app.services.test_patient_service._rule_stem`
    -- duplicated here to keep the terminology service free of an upstream
    import. Every rule edit appends ``:edit:<8 hex>`` to the predecessor id;
    the compiled bitmap only carries the head of the SUPERSEDES chain, so a
    saved rule_id may be one or more edits behind the active version. The
    stem (everything before the first ``:edit:``) is the stable logical
    identity reviewers actually care about when reading a diagnostic.
    """
    rid = (rule_id or "").strip()
    if not rid:
        return ""
    idx = rid.find(":edit:")
    return rid[:idx] if idx >= 0 else rid


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
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
        ruleset_version: str | None = None,
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
        if ruleset_version:
            ruleset = self._store.get_ruleset(
                ruleset_version,
                scope_type=scope_type,
                scope_id=scope_id,
            )
        else:
            ruleset = self._store.get_current_ruleset(
                scope_type=scope_type,
                scope_id=scope_id,
            )
        if not ruleset:
            logger.warning(
                "GuidelineEvaluator: no active ruleset found in Redis "
                "(scope=%s/%s) -- ALL patient evaluations will return zero "
                "matches. Run POST /guidelines/bitmap/compile to rebuild.",
                scope_type or "global",
                scope_id or "default",
            )
            return {
                "matched_rules": [],
                "active_version": None,
                "not_compiled": True,
                "message": "No active ruleset compiled yet.",
                "recompile_hint": (
                    "POST /terminology/guidelines/bitmap/compile "
                    f"with scope_type={scope_type or 'global'} "
                    f"scope_id={scope_id or 'default'}"
                ),
                "scope_type": scope_type or "global",
                "scope_id": scope_id or "default",
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
                matched_via = self._collect_matched_via(rule, patient_bitmap)
                matches.append(_format_match(rule, matched_via=matched_via))

        return {
            "matched_rules": matches,
            "active_version": ruleset.get("version"),
            "not_compiled": False,
            "compile_timestamp": ruleset.get("compile_timestamp"),
            "scope_type": ruleset.get("scope_type") or scope_type or "global",
            "scope_id": ruleset.get("scope_id") or scope_id or "default",
        }

    def diagnose(
        self,
        rule_id: str,
        patient_codes: list[str],
        patient_age: float | None = None,
        patient_sex: str | None = None,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
        ruleset_version: str | None = None,
    ) -> dict[str, Any] | None:
        """Return per-node match diagnostics for ONE rule.

        Uses the same bitmap operations as ``evaluate_patient`` so the
        diagnostic verdict is guaranteed to agree with the production
        firing decision. The annotated tree is returned in the same shape
        as the compiled ``logic_tree`` so the UI can render it
        hierarchically (preserving AND / OR / NOT / AT_LEAST semantics).
        """
        if ruleset_version:
            ruleset = self._store.get_ruleset(
                ruleset_version,
                scope_type=scope_type,
                scope_id=scope_id,
            )
        else:
            ruleset = self._store.get_current_ruleset(
                scope_type=scope_type,
                scope_id=scope_id,
            )
        if not ruleset:
            return {
                "rule_id": rule_id,
                "fires": False,
                "annotated_tree": None,
                "not_compiled": True,
                "rule_found": False,
                "message": "No active ruleset compiled yet.",
                "recompile_hint": (
                    "POST /terminology/guidelines/bitmap/compile "
                    f"with scope_type={scope_type or 'global'} "
                    f"scope_id={scope_id or 'default'}"
                ),
                "scope_type": scope_type or "global",
                "scope_id": scope_id or "default",
            }

        rules = ruleset.get("rules", [])
        rule = next((r for r in rules if r.get("rule_id") == rule_id), None)
        rebound_from: str | None = None
        if not rule:
            # Fall back to rule-stem match: every edit appends
            # ``:edit:<8 hex>`` to the predecessor id, so a saved rule_id
            # may be one or more edits behind (or ahead of) the active
            # version. Pick the longest descendant whose stem matches --
            # that is the most-edited variant currently compiled.
            stem = _rule_stem(rule_id)
            if stem:
                candidates = [r for r in rules if _rule_stem(r.get("rule_id")) == stem]
                if candidates:
                    rule = max(
                        candidates, key=lambda r: len(str(r.get("rule_id") or ""))
                    )
                    rebound_from = rule_id
        if not rule:
            return {
                "rule_id": rule_id,
                "fires": False,
                "annotated_tree": None,
                "not_compiled": False,
                "rule_found": False,
                "message": (
                    f"Rule {rule_id} not present in the active ruleset "
                    f"(version={ruleset.get('version')!r}). It may need "
                    "recompilation."
                ),
                "active_version": ruleset.get("version"),
                "scope_type": ruleset.get("scope_type") or scope_type or "global",
                "scope_id": ruleset.get("scope_id") or scope_id or "default",
            }

        effective_codes = list(patient_codes)
        if patient_sex:
            sex_code = _SEX_CODE.get(patient_sex.lower().strip())
            if sex_code and sex_code not in effective_codes:
                effective_codes.append(sex_code)
        patient_bm = self._build_patient_bitmap(effective_codes)

        annotated, fires = self._annotate_rule(
            rule, patient_bm, patient_age, patient_sex
        )

        resolved_count = sum(
            1 for c in effective_codes if self._store.get_int_id(c) is not None
        )
        result: dict[str, Any] = {
            "rule_id": rule.get("rule_id") or rule_id,
            "rule_name": rule.get("name"),
            "guideline_id": rule.get("guideline_id"),
            "schema_version": int(rule.get("schema_version") or 1),
            "fires": fires,
            "annotated_tree": annotated,
            "not_compiled": False,
            "rule_found": True,
            "patient": {
                "codes_provided": len(patient_codes),
                "codes_resolved": resolved_count,
                "age": patient_age,
                "sex": patient_sex,
            },
            "active_version": ruleset.get("version"),
            "scope_type": ruleset.get("scope_type") or scope_type or "global",
            "scope_id": ruleset.get("scope_id") or scope_id or "default",
        }
        if rebound_from and rebound_from != result["rule_id"]:
            result["requested_rule_id"] = rebound_from
            result["rebound_from"] = rebound_from
            result["rebind_reason"] = (
                f"Rule {rebound_from} has been edited; diagnosed against the "
                f"latest active version {result['rule_id']}."
            )
        return result

    def _annotate_rule(
        self,
        rule: dict,
        patient_bm: BitMap,
        patient_age: float | None,
        patient_sex: str | None,
    ) -> tuple[dict[str, Any] | None, bool]:
        """Return (annotated_tree, overall_fires) for any rule schema."""
        if int(rule.get("schema_version") or 1) == 2:
            tree = rule.get("logic_tree")
            annotated = self._annotate_logic_tree(
                tree, patient_bm, patient_age, patient_sex
            )
            fires = bool(annotated and annotated.get("matched"))
            return annotated, fires

        # Schema v1 -- synthesise a simple AND-of-groups tree so the UI
        # can render it the same way.
        applies_to = rule.get("applies_to") or []
        groups = rule.get("criteria_groups") or []
        children: list[dict[str, Any]] = []
        for idx, constraint in enumerate(applies_to):
            ok = _check_applies_to([constraint], patient_age)
            children.append(
                {
                    "kind": "DEMOGRAPHIC",
                    "node_id": f"applies_to_{idx}",
                    "field": "age",
                    "operator": constraint.get("operator"),
                    "value": constraint.get("value"),
                    "matched": ok,
                }
            )
        for idx, group in enumerate(groups):
            mode = str(group.get("mode", "ALL")).upper()
            bitmap_id = group.get("bitmap_id")
            bm = self._store.get_bitmap(bitmap_id) if bitmap_id else None
            if bm is None:
                ok = False
            elif mode == "ALL":
                ok = bm.issubset(patient_bm)
            elif mode == "ANY":
                ok = len(bm & patient_bm) > 0
            elif mode == "NOT":
                ok = len(bm & patient_bm) == 0
            else:
                ok = False
            children.append(
                {
                    "kind": "CONCEPT_GROUP",
                    "node_id": f"group_{idx}",
                    "mode": mode,
                    "matched": ok,
                }
            )
        if not children:
            return None, False
        overall = all(c.get("matched") for c in children)
        return (
            {
                "kind": "AND",
                "node_id": "v1_root",
                "children": children,
                "matched": overall,
            },
            overall,
        )

    def _annotate_logic_tree(
        self,
        node: dict[str, Any] | None,
        patient_bm: BitMap,
        patient_age: float | None,
        patient_sex: str | None,
    ) -> dict[str, Any] | None:
        if not node:
            return None
        kind = str(node.get("kind") or "").upper()
        node_id = node.get("node_id")
        if kind == "CONCEPT":
            bitmap_id = node.get("bitmap_id")
            bm = self._store.get_bitmap(bitmap_id) if bitmap_id else None
            criterion = dict(node.get("criterion") or {})
            seed_concept_ids = list(node.get("seed_concept_ids") or [])
            if bm is None:
                matched = False
                missing_bitmap = True
                match_count = 0
                matched_concept_ids: list[str] = []
            else:
                missing_bitmap = False
                match_count = len(bm & patient_bm)
                matched = match_count > 0
                matched_concept_ids = self._matched_seed_ids(
                    seed_concept_ids, patient_bm
                )
            return {
                "kind": "CONCEPT",
                "node_id": node_id,
                "criterion": criterion,
                "matched": matched,
                "match_count": match_count,
                "missing_bitmap": missing_bitmap,
                "matched_concept_ids": matched_concept_ids,
            }
        if kind == "DEMOGRAPHIC":
            matched = _check_demographic_node(node, patient_age, patient_sex)
            return {
                "kind": "DEMOGRAPHIC",
                "node_id": node_id,
                "field": node.get("field"),
                "operator": node.get("operator"),
                "value": node.get("value"),
                "unit": node.get("unit"),
                "matched": matched,
            }
        children_in = list(node.get("children") or [])
        children_out = [
            self._annotate_logic_tree(c, patient_bm, patient_age, patient_sex)
            for c in children_in
        ]
        children_out = [c for c in children_out if c is not None]
        true_count = sum(1 for c in children_out if c.get("matched"))
        if kind == "AND":
            matched = bool(children_out) and true_count == len(children_out)
        elif kind == "OR":
            matched = true_count > 0
        elif kind == "NOT":
            matched = len(children_out) == 1 and not children_out[0].get("matched")
        elif kind == "AT_LEAST":
            threshold = int(node.get("min") or 1)
            matched = true_count >= threshold
        else:
            matched = False
        out: dict[str, Any] = {
            "kind": kind,
            "node_id": node_id,
            "children": children_out,
            "matched": matched,
            "matched_count": true_count,
            "total_count": len(children_out),
        }
        if kind == "AT_LEAST":
            out["min"] = int(node.get("min") or 1)
        return out

    def _matched_seed_ids(
        self,
        seed_concept_ids: list[str],
        patient_bm: BitMap,
    ) -> list[str]:
        """Return the subset of ``seed_concept_ids`` present in the patient bitmap.

        Used to populate ``matched_concept_ids`` (per CONCEPT leaf) and
        ``matched_via`` (per matched rule) so callers can name which exact
        SNOMED code(s) caused the rule to fire (UN-LEO-AI-093, DI-LEO-AI-510).
        Empty input returns an empty list.
        """
        if not seed_concept_ids:
            return []
        out: list[str] = []
        for cid in seed_concept_ids:
            iid = self._store.get_int_id(cid)
            if iid is not None and iid in patient_bm:
                out.append(cid)
        return out

    def _collect_matched_via(
        self,
        rule: dict,
        patient_bm: BitMap,
    ) -> list[dict[str, Any]]:
        """Walk the compiled logic tree and return per-CONCEPT-leaf hit info.

        Returns one entry per CONCEPT leaf whose bitmap intersects with the
        patient bitmap, in tree-traversal order. Each entry has:

          - ``node_id``: the leaf's stable id
          - ``primary_concept_id``: the chip's preferred-term anchor
          - ``preferred_term``: chip label (best-effort)
          - ``matched_concept_ids``: which seed ids hit (>=1)

        Schema v1 rules (no ``logic_tree``) return an empty list; schema v1
        does not store enough information to attribute hits to a specific
        synonym seed. Callers that need attribution should recompile to v2.
        """
        if int(rule.get("schema_version") or 1) != 2:
            return []
        out: list[dict[str, Any]] = []

        def _walk(node: dict[str, Any] | None) -> None:
            if not node:
                return
            kind = str(node.get("kind") or "").upper()
            if kind == "CONCEPT":
                seed_ids = list(node.get("seed_concept_ids") or [])
                hits = self._matched_seed_ids(seed_ids, patient_bm)
                if hits:
                    criterion = dict(node.get("criterion") or {})
                    out.append(
                        {
                            "node_id": node.get("node_id"),
                            "primary_concept_id": (
                                criterion.get("primary_concept_id")
                                or criterion.get("snomed_concept_id")
                            ),
                            "preferred_term": criterion.get("preferred_term")
                            or criterion.get("term"),
                            "matched_concept_ids": hits,
                        }
                    )
                return
            for child in (node.get("children") or []):
                _walk(child)

        _walk(rule.get("logic_tree"))
        return out

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
            return self._logic_tree_matches(
                logic_tree, patient_bm, patient_age, patient_sex
            )

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
                    bitmap_id,
                    mode,
                    rule.get("rule_id"),
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
            return all(
                self._logic_tree_matches(child, patient_bm, patient_age, patient_sex)
                for child in children
            )
        if kind == "OR":
            return any(
                self._logic_tree_matches(child, patient_bm, patient_age, patient_sex)
                for child in children
            )
        if kind == "NOT":
            if len(children) != 1:
                logger.error(
                    "Schema v2 NOT node %r must contain exactly one child.",
                    node.get("node_id"),
                )
                return False
            return not self._logic_tree_matches(
                children[0], patient_bm, patient_age, patient_sex
            )
        if kind == "AT_LEAST":
            threshold = int(node.get("min") or 1)
            count = sum(
                1
                for child in children
                if self._logic_tree_matches(child, patient_bm, patient_age, patient_sex)
            )
            return count >= threshold
        logger.error("Unknown schema v2 logic node kind %r — failing CLOSED.", kind)
        return False


# Maps caller-supplied sex string to the SNOMED concept ID injected into
# the patient bitmap so sex-based HAS_CRITERIA rules fire automatically.
_SEX_CODE: dict[str, str] = {
    "female": "248152002",
    "f": "248152002",
    "male": "248153007",
    "m": "248153007",
}

# SNOMED age observable concept — used to identify age constraints in applies_to
_AGE_CONCEPT_ID = "424144002"

_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    ">=": lambda a, v: a >= v,
    ">": lambda a, v: a > v,
    "<=": lambda a, v: a <= v,
    "<": lambda a, v: a < v,
    "=": lambda a, v: a == v,
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
                    operator,
                    value,
                )
                return False
            op_fn = _OPERATORS.get(operator or ">=")
            if op_fn is None or value is None:
                logger.error(
                    "Unrecognised age constraint operator %r (value=%r) — "
                    "failing CLOSED: rule will not fire.",
                    operator,
                    value,
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
                concept_id,
                operator,
                value,
                concept_id,
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
            logger.error(
                "Invalid age logic node operator/value (%r, %r) — failing CLOSED.",
                operator,
                value,
            )
            return False
        return op_fn(patient_age, float(value))
    if field == "sex":
        if not patient_sex:
            logger.warning(
                "Sex logic node cannot be evaluated — patient_sex not supplied; failing CLOSED."
            )
            return False
        if operator != "=":
            logger.error(
                "Unsupported sex logic node operator %r — failing CLOSED.", operator
            )
            return False
        return patient_sex.lower().strip() == str(value or "").lower().strip()
    logger.error("Unknown demographic field %r — failing CLOSED.", field)
    return False


def _format_match(
    rule: dict,
    *,
    matched_via: list[dict[str, Any]] | None = None,
) -> dict:
    """Format a matched rule for the API response.

    ``matched_via`` (DI-LEO-AI-510) lists which exact SNOMED code(s) on the
    patient caused each CONCEPT chip in the rule to fire. The SBAR
    formatter uses this so narratives can say "matched on Cigarette
    smoker" rather than only naming the rule.
    """
    payload = {
        "rule_id": rule["rule_id"],
        "name": rule.get("name"),
        "strength": rule.get("strength"),
        "guideline_id": rule.get("guideline_id"),
        "guideline_title": rule.get("guideline_title"),
        "chapter_title": rule.get("chapter_title"),
        "recommendation_verbatim": rule.get("recommendation_verbatim"),
        "action": rule.get("action"),
        "confidence": 1.0,
    }
    if matched_via:
        payload["matched_via"] = matched_via
    return payload
