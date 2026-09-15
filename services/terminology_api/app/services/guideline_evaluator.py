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

import dataclasses
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from pyroaring import BitMap

from libs.guidelines.action_already_done import (
    all_actions_already_done,
    mark_already_done_actions,
)
from services.terminology_api.app.services.bitmap_store import BitmapStore
from services.terminology_api.app.services.observation_evaluator import (
    observation_matches,
)

logger = logging.getLogger(__name__)


def _rule_stem(rule_id: str | None) -> str:
    """Return the canonical rule identity, stripping any ``:edit:*`` chain.

    Every rule edit appends ``:edit:<8 hex>`` to the predecessor id;
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


def _collect_tree_bitmap_ids(node: dict[str, Any] | None) -> list[str]:
    """Walk a compiled logic tree and return all bitmap_id values.

    Used to pre-fetch the full set of CONCEPT-node bitmaps in a single
    Redis MGET before rule evaluation, replacing one GET per node with one
    round trip per ruleset.  May return duplicates; callers should deduplicate.
    """
    if not node:
        return []
    if str(node.get("kind") or "").upper() == "CONCEPT":
        bid = node.get("bitmap_id")
        return [bid] if bid else []
    out: list[str] = []
    for child in (node.get("children") or []):
        out.extend(_collect_tree_bitmap_ids(child))
    return out


def _collect_tree_seed_ids(node: dict[str, Any] | None) -> list[str]:
    """Walk a compiled logic tree and return all seed_concept_ids.

    Used to pre-fetch int_ids for every synonym seed in one Redis HMGET
    before _collect_matched_via, replacing one HGET per seed with one
    round trip per ruleset.  May return duplicates; callers should deduplicate.
    """
    if not node:
        return []
    if str(node.get("kind") or "").upper() == "CONCEPT":
        return list(node.get("seed_concept_ids") or [])
    out: list[str] = []
    for child in (node.get("children") or []):
        out.extend(_collect_tree_seed_ids(child))
    return out


@dataclasses.dataclass(slots=True)
class _PatientContext:
    """Patient clinical context passed through a single evaluate_patient call.

    Groups the per-patient inputs so helper methods stay within the
    parameter-count limit without losing type safety.
    """

    age: float | None
    sex: str | None
    observations: list[dict[str, Any]] | None
    medications: list[dict[str, Any]] | None
    allergies: list[dict[str, Any]] | None
    treatments: list[dict[str, Any]] | None
    letter_text: str = ""
    concept_occurrences: dict[str, list] = dataclasses.field(default_factory=dict)
    evaluation_time: Any = None
    unverified_qualifiers: list[str] = dataclasses.field(default_factory=list)


class _RuleEvaluationSession:
    """Per-patient lazy memoised evaluation session for RULE_FIRED chaining.

    Each rule is evaluated at most once per patient session (memoised).
    Circular dependencies are detected via ``_in_progress`` and return
    False (fail-closed) without raising an exception or looping.

    Atlas trace: DO-274E5A61 / DI-8899D4F3 / R-E60D1E76.
    """

    def __init__(
        self,
        evaluator: "GuidelineEvaluator",
        rules_by_id: dict[str, dict],
        patient_bm: "BitMap",
        ctx: _PatientContext,
        bitmap_cache: dict[str, "BitMap"],
    ) -> None:
        self._evaluator = evaluator
        self._rules_by_id = rules_by_id
        self._patient_bm = patient_bm
        self._ctx = ctx
        self._bitmap_cache = bitmap_cache
        self._cache: dict[str, bool] = {}
        self._in_progress: set[str] = set()

    def evaluate(self, rule_id: str) -> bool:
        if rule_id in self._cache:
            return self._cache[rule_id]
        if rule_id in self._in_progress:
            logger.warning(
                "RULE_FIRED circular dependency for rule %r -- returning False (fail-closed).",
                rule_id,
            )
            return False
        rule = self._rules_by_id.get(rule_id)
        if rule is None:
            logger.warning(
                "RULE_FIRED references unknown rule_id %r -- returning False (fail-closed).",
                rule_id,
            )
            self._cache[rule_id] = False
            return False
        self._in_progress.add(rule_id)
        try:
            result = self._evaluator._rule_matches(
                rule,
                self._patient_bm,
                self._ctx.age,
                self._ctx.sex,
                patient_observations=self._ctx.observations,
                active_medications=self._ctx.medications,
                allergies=self._ctx.allergies,
                treatment_history=self._ctx.treatments,
                bitmap_cache=self._bitmap_cache,
                session=self,
            )
        except Exception:
            logger.exception(
                "RULE_FIRED evaluation of rule %r raised an exception -- fail-closed.",
                rule_id,
            )
            result = False
        finally:
            self._in_progress.discard(rule_id)
        self._cache[rule_id] = result
        return result


class GuidelineEvaluator:
    """Evaluates a patient's SNOMED code set against the active ruleset.

    Loads the active ruleset from Redis on each call. The ruleset is small
    (typically a few KB of JSON) and Redis is local or low-latency, so the
    load overhead is negligible.
    """

    def __init__(self, store: BitmapStore | None = None, neo4j_session=None) -> None:
        self._store = store or BitmapStore()
        self._neo4j_session = neo4j_session

    def _make_related_lookup(self) -> Callable[[str], dict[str, Any]] | None:
        """Build a SNOMED concept-neighbour lookup backed by the Neo4j session.

        Returns None when no session is available so callers degrade gracefully.
        The lookup is used by mark_already_done_actions at evaluation time to
        traverse Interprets / HAS_COMPONENT relationships for concepts that
        were not pre-compiled into already_done_evidence_ids.
        """
        if self._neo4j_session is None:
            return None
        session = self._neo4j_session

        def _lookup(concept_id: str) -> dict[str, Any]:
            from services.terminology_api.app.services.guideline_compiler import (
                GuidelineCompiler,
            )

            result = GuidelineCompiler._snomed_related_dict(concept_id, session)
            return result or {}

        return _lookup

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
        patient_observations: list[dict[str, Any]] | None = None,
        active_medications: list[dict[str, Any]] | None = None,
        allergies: list[dict[str, Any]] | None = None,
        treatment_history: list[dict[str, Any]] | None = None,
        letter_text: str | None = None,
        concept_occurrences: dict[str, list] | None = None,
        evaluation_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Evaluate patient SNOMED codes against the active bitmap ruleset.

        Args:
            patient_codes: List of SNOMED concept ID strings for the patient.
            pathway_filter: Optional guideline ID to restrict evaluation to one
                            guideline (e.g. ``NG151``).
            patient_age: Patient age in years (decimal).  Required for rules
                         with age-based ``APPLIES_TO`` constraints.
            patient_sex: PDS administrative gender value.  Accepted values:
                         ``"male"`` or ``"female"`` (binary -- rules applied,
                         limitation notice returned), ``"other"`` or
                         ``"unknown"`` (unusable -- gender-specific rules not
                         applied, clinician-review flag set), or ``None`` (no
                         PDS gender supplied -- existing fail-closed behaviour).

        Returns:
            Dict with ``matched_rules``, ``active_version``, and PDS gender
            fields: ``gender_review_flag``, ``gender_review_reason``,
            ``limitation_notice``, ``gender_basis``,
            ``gender_sensitive_rules_skipped``.
        """
        ruleset = self._load_ruleset(ruleset_version, scope_type, scope_id)
        if not ruleset:
            logger.warning(
                "GuidelineEvaluator: no active ruleset for scope=%s/%s.",
                scope_type or "global",
                scope_id or "default",
            )
            return _not_compiled_response(scope_type, scope_id)

        requires_review, review_reason, limitation_notice = _check_pds_gender_gate(
            patient_sex
        )
        rules = ruleset.get("rules", [])
        skipped = _count_sex_sensitive_rules(rules) if requires_review else 0

        if not requires_review and _check_anatomy_conflict(patient_codes, patient_sex):
            requires_review = True
            review_reason = "anatomy_conflict"
            limitation_notice = None
            gender_basis: str | None = "anatomy_evidence"
        else:
            gender_basis = "pds_gender" if patient_sex else None

        effective_codes = list(patient_codes)
        if not requires_review and patient_sex:
            sex_code = _SEX_CODE.get(patient_sex.lower().strip())
            if sex_code and sex_code not in effective_codes:
                effective_codes.append(sex_code)

        ctx = _PatientContext(
            age=patient_age,
            sex=patient_sex,
            observations=patient_observations,
            medications=active_medications,
            allergies=allergies,
            treatments=treatment_history,
            letter_text=letter_text or "",
            concept_occurrences=concept_occurrences or {},
            evaluation_time=evaluation_time,
        )
        patient_bitmap = self._build_patient_bitmap(effective_codes)
        bitmap_cache, int_id_cache = _prefetch_rule_caches(rules, self._store)
        matches = self._collect_matches(
            rules,
            patient_bitmap,
            pathway_filter,
            ctx,
            bitmap_cache,
            int_id_cache,
            patient_codes=effective_codes,
        )
        overall = None
        if matches:
            from libs.guidelines.soft_qualifier import overall_investigation_status

            overall = overall_investigation_status(
                [m.get("investigation_status") for m in matches]
            )
            if overall == "exempt":
                for match in matches:
                    if match.get("investigation_status"):
                        match["investigation_status"] = "exempt"
        return {
            "matched_rules": matches,
            "investigation_status": overall,
            "active_version": ruleset.get("version"),
            "not_compiled": False,
            "compile_timestamp": ruleset.get("compile_timestamp"),
            "scope_type": ruleset.get("scope_type") or scope_type or "global",
            "scope_id": ruleset.get("scope_id") or scope_id or "default",
            "gender_review_flag": requires_review,
            "gender_review_reason": review_reason,
            "limitation_notice": limitation_notice,
            "gender_basis": gender_basis,
            "gender_sensitive_rules_skipped": skipped,
        }

    def _load_ruleset(
        self,
        ruleset_version: str | None,
        scope_type: str | None,
        scope_id: str | None,
    ) -> dict[str, Any] | None:
        """Return the requested or current ruleset from the store."""
        if ruleset_version:
            return self._store.get_ruleset(
                ruleset_version,
                scope_type=scope_type,
                scope_id=scope_id,
            )
        return self._store.get_current_ruleset(
            scope_type=scope_type,
            scope_id=scope_id,
        )

    def _collect_matches(
        self,
        rules: list[dict],
        patient_bitmap: BitMap,
        pathway_filter: str | None,
        ctx: _PatientContext,
        bitmap_cache: dict[str, BitMap],
        int_id_cache: dict[str, int],
        patient_codes: list[str] | None = None,
    ) -> list[dict]:
        """Run the rule-matching loop and return formatted matches."""
        rules_by_id = {r["rule_id"]: r for r in rules if r.get("rule_id")}
        session = _RuleEvaluationSession(
            self, rules_by_id, patient_bitmap, ctx, bitmap_cache
        )
        matches = []
        codes = patient_codes or []
        for rule in rules:
            if pathway_filter and rule.get("guideline_id") != pathway_filter:
                continue
            rule_id = rule.get("rule_id", "")
            ctx.unverified_qualifiers.clear()
            if not session.evaluate(rule_id):
                continue
            matched_via = self._collect_firing_path_matched_via(
                rule,
                patient_bitmap,
                ctx,
                bitmap_cache,
                session=session,
            )
            payload = mark_already_done_actions(
                _format_match(
                    rule,
                    matched_via=matched_via,
                    unverified_qualifiers=list(ctx.unverified_qualifiers),
                    patient_codes=codes,
                    observations=ctx.observations,
                ),
                codes,
                ctx.observations,
                related_lookup=self._make_related_lookup(),
            )
            matches.append(payload)
        return matches

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
        patient_observations: list[dict[str, Any]] | None = None,
        active_medications: list[dict[str, Any]] | None = None,
        allergies: list[dict[str, Any]] | None = None,
        treatment_history: list[dict[str, Any]] | None = None,
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

        # Build a RULE_FIRED session so chained rules can be resolved in the
        # diagnose path with the same fail-closed cycle guard as evaluate_patient.
        _diag_ctx = _PatientContext(
            age=patient_age,
            sex=patient_sex,
            observations=patient_observations,
            medications=active_medications,
            allergies=allergies,
            treatments=treatment_history,
        )
        _all_rules = ruleset.get("rules") or []
        _rules_by_id = {r["rule_id"]: r for r in _all_rules if r.get("rule_id")}
        _diag_session = _RuleEvaluationSession(
            self, _rules_by_id, patient_bm, _diag_ctx, {}
        )

        annotated, fires = self._annotate_rule(
            rule,
            patient_bm,
            patient_age,
            patient_sex,
            patient_observations=patient_observations,
            active_medications=active_medications,
            allergies=allergies,
            treatment_history=treatment_history,
            session=_diag_session,
        )
        already_actioned = bool(
            fires
            and all_actions_already_done(rule, effective_codes, patient_observations)
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
            "already_actioned": already_actioned,
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
        *,
        patient_observations: list[dict[str, Any]] | None = None,
        active_medications: list[dict[str, Any]] | None = None,
        allergies: list[dict[str, Any]] | None = None,
        treatment_history: list[dict[str, Any]] | None = None,
        session: "_RuleEvaluationSession | None" = None,
    ) -> tuple[dict[str, Any] | None, bool]:
        """Return (annotated_tree, overall_fires) for any rule schema."""
        if int(rule.get("schema_version") or 1) == 2:
            tree = rule.get("logic_tree")
            annotated = self._annotate_logic_tree(
                tree,
                patient_bm,
                patient_age,
                patient_sex,
                patient_observations=patient_observations,
                active_medications=active_medications,
                allergies=allergies,
                treatment_history=treatment_history,
                session=session,
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
        *,
        patient_observations: list[dict[str, Any]] | None = None,
        active_medications: list[dict[str, Any]] | None = None,
        allergies: list[dict[str, Any]] | None = None,
        treatment_history: list[dict[str, Any]] | None = None,
        session: "_RuleEvaluationSession | None" = None,
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
                if matched:
                    matched = self._soft_concept_allows(
                        node, session, record_unverified=False
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
        if kind == "OBSERVATION":
            matched = observation_matches(
                node,
                patient_observations,
                patient_sex=patient_sex,
                patient_age=patient_age,
            )
            return {
                "kind": "OBSERVATION",
                "node_id": node_id,
                "observable_id": node.get("observable_id"),
                "observable_term": node.get("observable_term"),
                "operator": node.get("operator"),
                "value": node.get("value"),
                "unit": node.get("unit"),
                "wire_unit": node.get("wire_unit"),
                "within_days": node.get("within_days"),
                "mode": _observation_mode(node),
                "matched": matched,
            }
        if kind == "MEDICATION":
            matched, reason, source_ids = self._medication_matches(
                node, active_medications or []
            )
            return {
                "kind": "MEDICATION",
                "node_id": node_id,
                "drug_class": node.get("drug_class"),
                "concept_id": node.get("concept_id"),
                "term": node.get("term"),
                "matched": matched,
                "reason": reason,
                "source_ids": source_ids,
            }
        if kind == "ALLERGY":
            matched, reason, source_ids = self._allergy_matches(
                node, allergies or []
            )
            return {
                "kind": "ALLERGY",
                "node_id": node_id,
                "substance_concept_id": node.get("substance_concept_id"),
                "allergy_class": node.get("allergy_class"),
                "term": node.get("term"),
                "matched": matched,
                "reason": reason,
                "source_ids": source_ids,
            }
        if kind == "TREATMENT_HISTORY":
            matched, reason, source_ids = self._treatment_history_matches(
                node, treatment_history or []
            )
            return {
                "kind": "TREATMENT_HISTORY",
                "node_id": node_id,
                "treatment_class": node.get("treatment_class"),
                "min_duration_days": node.get("min_duration_days"),
                "term": node.get("term"),
                "matched": matched,
                "reason": reason,
                "source_ids": source_ids,
            }
        if kind == "RULE_FIRED":
            ref_id = node.get("referenced_rule_id") or ""
            outcome = str(node.get("outcome") or "fired")
            if session is not None and ref_id:
                fired = session.evaluate(ref_id)
                matched = fired if outcome == "fired" else not fired
            else:
                matched = False
            return {
                "kind": "RULE_FIRED",
                "node_id": node_id,
                "referenced_rule_id": ref_id,
                "display_name": node.get("display_name"),
                "outcome": outcome,
                "matched": matched,
            }
        _ann_kwargs: dict[str, Any] = {
            "patient_observations": patient_observations,
            "active_medications": active_medications,
            "allergies": allergies,
            "treatment_history": treatment_history,
            "session": session,
        }
        children_in = list(node.get("children") or [])
        children_out = [
            self._annotate_logic_tree(
                c,
                patient_bm,
                patient_age,
                patient_sex,
                **_ann_kwargs,
            )
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
        int_id_cache: dict[str, int] | None = None,
    ) -> list[str]:
        """Return the subset of ``seed_concept_ids`` present in the patient bitmap.

        Used to populate ``matched_concept_ids`` (per CONCEPT leaf) and
        ``matched_via`` (per matched rule) so callers can name which exact
        SNOMED code(s) caused the rule to fire (UN-LEO-AI-093, DI-LEO-AI-510).
        Empty input returns an empty list.

        Args:
            int_id_cache: Optional pre-fetched mapping from concept_id to
                int_id (built via get_int_ids_bulk).  When supplied, avoids
                per-seed Redis HGET calls.
        """
        if not seed_concept_ids:
            return []
        out: list[str] = []
        for cid in seed_concept_ids:
            if int_id_cache is not None:
                iid = int_id_cache.get(cid)
            else:
                iid = self._store.get_int_id(cid)
            if iid is not None and iid in patient_bm:
                out.append(cid)
        return out

    def _collect_matched_via(
        self,
        rule: dict,
        patient_bm: BitMap,
        int_id_cache: dict[str, int] | None = None,
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

        Args:
            int_id_cache: Optional pre-fetched mapping from concept_id to
                int_id (built via get_int_ids_bulk).  When supplied, avoids
                per-seed Redis HGET calls inside _matched_seed_ids.
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
                hits = self._matched_seed_ids(
                    seed_ids, patient_bm, int_id_cache=int_id_cache
                )
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

    def _collect_firing_path_matched_via(
        self,
        rule: dict,
        patient_bm: BitMap,
        ctx: _PatientContext,
        bitmap_cache: dict[str, BitMap],
        *,
        session: _RuleEvaluationSession | None = None,
    ) -> list[dict[str, Any]]:
        """Return matched leaves from the firing branch for SBAR attribution."""
        if int(rule.get("schema_version") or 1) != 2:
            return _applies_to_demographic_matched_via(rule, ctx.age)
        logic_tree = rule.get("logic_tree")
        if not logic_tree:
            return []
        annotated = self._annotate_logic_tree(
            logic_tree,
            patient_bm,
            ctx.age,
            ctx.sex,
            patient_observations=ctx.observations,
            active_medications=ctx.medications or [],
            allergies=ctx.allergies or [],
            treatment_history=ctx.treatments or [],
            session=session,
        )
        if not annotated or not annotated.get("matched"):
            return []
        return _matched_via_from_firing_path(annotated, ctx.age, ctx.sex)

    def _build_patient_bitmap(self, concept_ids: list[str]) -> BitMap:
        """Map patient concept IDs to integer IDs and build a BitMap.

        Uses a single Redis HMGET round trip for all concept IDs so that
        evaluation latency does not scale linearly with the number of
        patient codes (important when Redis is on Azure with TLS latency).

        Concept IDs not yet in the store are silently skipped --
        unknown codes cannot match any rule.

        Args:
            concept_ids: Patient SNOMED concept ID strings.

        Returns:
            PyRoaring BitMap containing mapped integer IDs.
        """
        id_map = self._store.get_int_ids_bulk(list(concept_ids))
        return BitMap(id_map.values())

    @staticmethod
    def _medication_matches(
        node: dict[str, Any],
        active_medications: list[dict[str, Any]],
    ) -> tuple[bool, str, list[str]]:
        """Match a MEDICATION leaf against the patient's active medications.

        Atlas trace: DO-0EC3A9CB / DI-2199E670

        Returns:
            (matched, reason, source_ids)
        Fail-closed: any status other than "active" fails. Empty list fails.
        """
        drug_class = (node.get("drug_class") or "").strip()
        concept_id = node.get("concept_id")
        if not active_medications:
            return False, "no medication data available -- fail closed", []
        for med in active_medications:
            if med.get("status") != "active":
                continue
            class_match = med.get("drug_class") == drug_class
            if not class_match:
                continue
            if concept_id and med.get("concept_id") and med["concept_id"] != concept_id:
                continue
            return True, f"active {drug_class} medication matched", list(
                med.get("source_ids") or []
            )
        return False, f"no active {drug_class} medication found -- fail closed", []

    @staticmethod
    def _allergy_matches(
        node: dict[str, Any],
        allergies: list[dict[str, Any]],
    ) -> tuple[bool, str, list[str]]:
        """Match an ALLERGY leaf against the patient's allergy list.

        Atlas trace: DO-0EC3A9CB / DI-2199E670

        Returns:
            (matched, reason, source_ids)
        nkda and unknown produce different reasons; both fail closed.
        Empty list fails closed (different reason from nkda).
        """
        substance_concept_id = node.get("substance_concept_id", "")
        allergy_class = node.get("allergy_class")
        if not allergies:
            return False, "no allergy information available -- fail closed", []
        for allergy in allergies:
            status = allergy.get("status", "unknown")
            if status == "nkda":
                return (
                    False,
                    "documented no known drug allergies -- fail closed",
                    [],
                )
            if status != "active":
                continue
            concept_match = allergy.get("substance_concept_id") == substance_concept_id
            class_match = (
                allergy_class
                and allergy.get("allergy_class") == allergy_class
            )
            if concept_match or class_match:
                return True, f"active allergy to {substance_concept_id} matched", list(
                    allergy.get("source_ids") or []
                )
        return (
            False,
            f"no active allergy to {substance_concept_id} found -- fail closed",
            [],
        )

    @staticmethod
    def _treatment_history_matches(
        node: dict[str, Any],
        treatment_history: list[dict[str, Any]],
    ) -> tuple[bool, str, list[str]]:
        """Match a TREATMENT_HISTORY leaf against the patient's treatment history.

        Atlas trace: DO-0EC3A9CB / DI-2199E670

        Returns:
            (matched, reason, source_ids)
        Only "failed" and "not_tolerated" outcomes pass.
        min_duration_days check fails closed when duration is absent.
        """
        _MATCHING_OUTCOMES = {"failed", "not_tolerated"}
        treatment_class = (node.get("treatment_class") or "").strip()
        min_duration = node.get("min_duration_days")
        concept_id = node.get("concept_id")
        if not treatment_history:
            return False, "no treatment history available -- fail closed", []
        for tx in treatment_history:
            if tx.get("treatment_class") != treatment_class:
                continue
            outcome = tx.get("outcome", "unknown")
            if outcome not in _MATCHING_OUTCOMES:
                continue
            if concept_id and tx.get("concept_id") and tx["concept_id"] != concept_id:
                continue
            if min_duration is not None:
                tx_duration = tx.get("duration_days")
                if tx_duration is None:
                    return (
                        False,
                        f"{treatment_class} trial duration not recorded"
                        " -- fail closed",
                        [],
                    )
                if tx_duration < min_duration:
                    continue
            return (
                True,
                f"{treatment_class} trial with outcome {outcome} matched",
                list(tx.get("source_ids") or []),
            )
        return (
            False,
            f"no {treatment_class} trial with required outcome found -- fail closed",
            [],
        )

    def _rule_matches(
        self,
        rule: dict,
        patient_bm: BitMap,
        patient_age: float | None = None,
        patient_sex: str | None = None,
        *,
        patient_observations: list[dict[str, Any]] | None = None,
        active_medications: list[dict[str, Any]] | None = None,
        allergies: list[dict[str, Any]] | None = None,
        treatment_history: list[dict[str, Any]] | None = None,
        bitmap_cache: dict[str, BitMap] | None = None,
        session: "_RuleEvaluationSession | None" = None,
    ) -> bool:
        """Return True if a compiled rule matches the patient bitmap.

        Evaluation order:
        1. ``APPLIES_TO`` demographic constraints (age) -- any unmet constraint
           immediately disqualifies the rule.
        2. ``criteria_groups`` -- each group is evaluated by its mode (ALL/ANY/NOT).
           ALL groups must pass (AND between groups).

        A rule with no groups and no applies_to cannot match any patient and
        returns False.

        Args:
            rule: Compiled rule dict from the ruleset.
            patient_bm: Patient BitMap built from their SNOMED codes.
            patient_age: Patient age in decimal years for age constraint checks.
            bitmap_cache: Optional pre-fetched mapping from bitmap_id to BitMap
                (built via get_bitmaps_bulk).  When supplied, avoids per-node
                Redis GET calls.

        Returns:
            True if the patient satisfies all criteria.
        """
        if int(rule.get("schema_version") or 1) == 2:
            logic_tree = rule.get("logic_tree")
            if not logic_tree:
                return False
            return self._logic_tree_matches(
                logic_tree,
                patient_bm,
                patient_age,
                patient_sex,
                patient_observations=patient_observations,
                active_medications=active_medications or [],
                allergies=allergies or [],
                treatment_history=treatment_history or [],
                bitmap_cache=bitmap_cache,
                session=session,
            )

        applies_to = rule.get("applies_to") or []
        if applies_to and not _check_applies_to(applies_to, patient_age):
            return False

        criteria_groups = rule.get("criteria_groups") or []
        if not criteria_groups:
            # A rule with only applies_to constraints (no bitmap groups) fires when
            # the demographic gate passes -- only if applies_to is non-empty.
            return bool(applies_to)

        any_group_evaluated = False
        for group in criteria_groups:
            bitmap_id = group.get("bitmap_id")
            if not bitmap_id:
                continue
            mode = str(group.get("mode", "ALL")).upper()
            bm = (
                bitmap_cache.get(bitmap_id)
                if bitmap_cache is not None
                else None
            ) or self._store.get_bitmap(bitmap_id)
            if bm is None:
                # A missing bitmap means Redis data is corrupt or was evicted.
                # We CANNOT safely evaluate this group in any mode:
                #   ALL missing -> cannot confirm required criteria are met
                #   ANY missing -> cannot confirm at least one criterion is met
                #   NOT missing -> cannot confirm exclusion criteria are absent
                # In all cases, fail CLOSED (do not fire the rule).
                logger.error(
                    "Bitmap %r for mode=%s group of rule %r is MISSING from Redis -- "
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
        *,
        patient_observations: list[dict[str, Any]] | None = None,
        active_medications: list[dict[str, Any]] | None = None,
        allergies: list[dict[str, Any]] | None = None,
        treatment_history: list[dict[str, Any]] | None = None,
        bitmap_cache: dict[str, BitMap] | None = None,
        session: "_RuleEvaluationSession | None" = None,
    ) -> bool:
        """Recursively evaluate a compiled logic tree node against a patient bitmap.

        Args:
            bitmap_cache: Optional pre-fetched mapping from bitmap_id to BitMap
                (built via get_bitmaps_bulk).  When supplied, avoids per-node
                Redis GET calls in CONCEPT leaves.
        """
        if not node:
            return False
        kind = str(node.get("kind") or "").upper()
        if kind == "CONCEPT":
            bitmap_id = node.get("bitmap_id")
            bm = (
                bitmap_cache.get(bitmap_id)
                if bitmap_cache is not None and bitmap_id
                else None
            ) or (self._store.get_bitmap(bitmap_id) if bitmap_id else None)
            if bm is None:
                logger.error(
                    "Schema v2 bitmap %r for rule node %r is missing from Redis"
                    " -- failing CLOSED.",
                    bitmap_id,
                    node.get("node_id"),
                )
                return False
            if len(bm & patient_bm) == 0:
                return False
            return self._soft_concept_allows(node, session)
        if kind == "DEMOGRAPHIC":
            return _check_demographic_node(node, patient_age, patient_sex)
        if kind == "OBSERVATION":
            return observation_matches(
                node,
                patient_observations,
                patient_sex=patient_sex,
                patient_age=patient_age,
            )
        if kind == "MEDICATION":
            matched, _reason, _src = self._medication_matches(
                node, active_medications or []
            )
            return matched
        if kind == "ALLERGY":
            matched, _reason, _src = self._allergy_matches(
                node, allergies or []
            )
            return matched
        if kind == "TREATMENT_HISTORY":
            matched, _reason, _src = self._treatment_history_matches(
                node, treatment_history or []
            )
            return matched
        if kind == "RULE_FIRED":
            if session is None:
                logger.error(
                    "RULE_FIRED leaf %r evaluated without a session -- returning False (fail-closed).",
                    node.get("node_id"),
                )
                return False
            ref_id = node.get("referenced_rule_id") or ""
            outcome = str(node.get("outcome") or "fired")
            fired = session.evaluate(ref_id)
            return fired if outcome == "fired" else not fired
        children = list(node.get("children") or [])
        _kwargs: dict[str, Any] = {
            "patient_observations": patient_observations,
            "active_medications": active_medications,
            "allergies": allergies,
            "treatment_history": treatment_history,
            "bitmap_cache": bitmap_cache,
            "session": session,
        }
        if kind == "AND":
            return all(
                self._logic_tree_matches(
                    child, patient_bm, patient_age, patient_sex, **_kwargs
                )
                for child in children
            )
        if kind == "OR":
            return any(
                self._logic_tree_matches(
                    child, patient_bm, patient_age, patient_sex, **_kwargs
                )
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
                children[0], patient_bm, patient_age, patient_sex, **_kwargs
            )
        if kind == "AT_LEAST":
            threshold = int(node.get("min") or 1)
            count = sum(
                1
                for child in children
                if self._logic_tree_matches(
                    child, patient_bm, patient_age, patient_sex, **_kwargs
                )
            )
            return count >= threshold
        logger.error("Unknown schema v2 logic node kind %r -- failing CLOSED.", kind)
        return False

    def _soft_concept_allows(
        self,
        node: dict[str, Any],
        session: "_RuleEvaluationSession | None",
        record_unverified: bool = True,
    ) -> bool:
        """Apply soft guideline words after the hard CONCEPT bitmap hit."""
        quals = (node.get("criterion") or {}).get("soft_qualifiers") or []
        if not quals:
            return True
        try:
            from libs.guidelines.soft_qualifier import apply_soft_qualifiers
        except Exception:
            logger.exception(
                "soft qualifier resolver unavailable -- fail closed"
            )
            raise
        if session is None:
            logger.error(
                "soft qualifiers evaluated without patient context -- fail closed"
            )
            return False
        ctx = session._ctx
        now = ctx.evaluation_time or datetime.now(timezone.utc)
        facts = {
            "letter_text": ctx.letter_text,
            "concept_occurrences": ctx.concept_occurrences,
        }
        sink = ctx.unverified_qualifiers if record_unverified else []
        return apply_soft_qualifiers(node, facts, now, sink)


def _observation_mode(node: dict[str, Any]) -> str:
    """Return which OBSERVATION evaluation mode is active in a compiled leaf.

    Mirrors the priority order in libs.guidance_schema.observation_leaf
    so the diagnose payload labels each leaf the same way the
    schema validator does.
    """
    if node.get("temporal"):
        return "temporal"
    if node.get("reference_range"):
        return "reference_range"
    if node.get("trend"):
        return "trend"
    if node.get("aggregation"):
        return "aggregate"
    return "absolute"


# Maps caller-supplied sex string to the SNOMED concept ID injected into
# the patient bitmap so sex-based HAS_CRITERIA rules fire automatically.
_SEX_CODE: dict[str, str] = {
    "female": "248152002",
    "f": "248152002",
    "male": "248153007",
    "m": "248153007",
}

# PDS gender values that cannot be used to drive anatomy-specific NICE rules.
_PDS_UNUSABLE_SEX: frozenset[str] = frozenset({"other", "unknown"})

# Limitation notice returned whenever binary PDS gender is used for anatomy-
# specific rules (DI-9AA2CDA5 clause b).
_LIMITATION_NOTICE: str = (
    "PDS administrative gender does not confirm reproductive anatomy. "
    "Check whether the patient has relevant reproductive organs before "
    "acting on anatomy-specific recommendations."
)

# Reproductive anatomy SNOMED codes split by expected PDS gender.
# Used to detect anatomy/gender conflicts (DI-9AA2CDA5 clause c).
_FEMALE_ANATOMY_SNOMED: frozenset[str] = frozenset(
    {
        "71252005",  # cervix uteri
        "35039007",  # uterus
        "15497006",  # ovary structure
        "31435000",  # fallopian tube
    }
)
_MALE_ANATOMY_SNOMED: frozenset[str] = frozenset(
    {
        "41216001",  # prostate gland
        "40689003",  # testis
    }
)

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
        if operator == "between":
            if not (isinstance(value, (list, tuple)) and len(value) == 2):
                logger.error(
                    "Age 'between' logic node requires value=[low, high], got %r — failing CLOSED.",
                    value,
                )
                return False
            try:
                low, high = float(value[0]), float(value[1])
            except (TypeError, ValueError):
                logger.error("Age 'between' value not numeric (%r) — failing CLOSED.", value)
                return False
            return low <= patient_age <= high
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


def _matched_via_dedupe_key(entry: dict[str, Any]) -> str:
    kind = str(entry.get("kind") or "").upper()
    if kind == "DEMOGRAPHIC":
        return f"demo:{entry.get('field')}"
    if kind == "CONCEPT":
        return f"concept:{entry.get('node_id') or entry.get('primary_concept_id')}"
    if kind == "OBSERVATION":
        return f"obs:{entry.get('node_id') or entry.get('observable_term')}"
    if kind == "MEDICATION":
        return f"med:{entry.get('node_id') or entry.get('drug_class')}"
    if kind == "ALLERGY":
        return f"allergy:{entry.get('node_id') or entry.get('allergy_class')}"
    if kind == "TREATMENT_HISTORY":
        return f"tx:{entry.get('node_id') or entry.get('treatment_class')}"
    if kind == "RULE_FIRED":
        return f"rule:{entry.get('referenced_rule_id')}"
    return f"other:{entry.get('node_id')}"


def _dedupe_matched_via_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for entry in entries:
        key = _matched_via_dedupe_key(entry)
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out


def _matched_via_entry_from_annotated_leaf(
    node: dict[str, Any],
    patient_age: float | None,
    patient_sex: str | None,
) -> dict[str, Any] | None:
    kind = str(node.get("kind") or "").upper()
    if kind == "DEMOGRAPHIC":
        return _demographic_matched_via_entry(node, patient_age, patient_sex)
    if kind == "CONCEPT":
        hits = list(node.get("matched_concept_ids") or [])
        if not hits:
            return None
        criterion = dict(node.get("criterion") or {})
        return {
            "kind": "CONCEPT",
            "node_id": node.get("node_id"),
            "primary_concept_id": (
                criterion.get("primary_concept_id")
                or criterion.get("snomed_concept_id")
            ),
            "preferred_term": criterion.get("preferred_term") or criterion.get("term"),
            "matched_concept_ids": hits,
        }
    if kind == "OBSERVATION":
        term = str(node.get("observable_term") or node.get("observable_id") or "").strip()
        if not term:
            return None
        return {
            "kind": "OBSERVATION",
            "node_id": node.get("node_id"),
            "observable_term": term,
            "operator": node.get("operator"),
            "value": node.get("value"),
            "unit": node.get("unit") or node.get("wire_unit"),
            "mode": node.get("mode"),
        }
    if kind == "MEDICATION":
        label = str(node.get("term") or node.get("drug_class") or "").strip()
        if not label:
            return None
        return {
            "kind": "MEDICATION",
            "node_id": node.get("node_id"),
            "term": label,
            "drug_class": node.get("drug_class"),
        }
    if kind == "ALLERGY":
        label = str(node.get("term") or node.get("allergy_class") or "").strip()
        if not label:
            return None
        return {
            "kind": "ALLERGY",
            "node_id": node.get("node_id"),
            "term": label,
            "allergy_class": node.get("allergy_class"),
        }
    if kind == "TREATMENT_HISTORY":
        label = str(node.get("term") or node.get("treatment_class") or "").strip()
        if not label:
            return None
        return {
            "kind": "TREATMENT_HISTORY",
            "node_id": node.get("node_id"),
            "term": label,
            "treatment_class": node.get("treatment_class"),
        }
    if kind == "RULE_FIRED":
        label = str(node.get("display_name") or node.get("referenced_rule_id") or "").strip()
        if not label:
            return None
        return {
            "kind": "RULE_FIRED",
            "node_id": node.get("node_id"),
            "display_name": label,
            "referenced_rule_id": node.get("referenced_rule_id"),
            "outcome": node.get("outcome"),
        }
    return None


def _matched_via_from_firing_path(
    node: dict[str, Any],
    patient_age: float | None,
    patient_sex: str | None,
) -> list[dict[str, Any]]:
    if not node or not node.get("matched"):
        return []
    kind = str(node.get("kind") or "").upper()
    if kind in {
        "CONCEPT",
        "DEMOGRAPHIC",
        "OBSERVATION",
        "MEDICATION",
        "ALLERGY",
        "TREATMENT_HISTORY",
        "RULE_FIRED",
    }:
        entry = _matched_via_entry_from_annotated_leaf(node, patient_age, patient_sex)
        return [entry] if entry else []
    if kind == "OR":
        for child in node.get("children") or []:
            if child.get("matched"):
                return _matched_via_from_firing_path(child, patient_age, patient_sex)
        return []
    if kind in {"AND", "AT_LEAST"}:
        merged: list[dict[str, Any]] = []
        for child in node.get("children") or []:
            if child.get("matched"):
                merged.extend(
                    _matched_via_from_firing_path(child, patient_age, patient_sex)
                )
        return _dedupe_matched_via_entries(merged)
    return []


def _demographic_matched_via_entry(
    node: dict[str, Any],
    patient_age: float | None,
    patient_sex: str | None,
) -> dict[str, Any]:
    field = str(node.get("field") or "").lower()
    entry: dict[str, Any] = {
        "kind": "DEMOGRAPHIC",
        "field": field,
        "operator": node.get("operator"),
        "value": node.get("value"),
        "unit": node.get("unit"),
    }
    if field == "age":
        entry["patient_value"] = patient_age
    elif field == "sex":
        entry["patient_value"] = patient_sex
    return entry


def _applies_to_demographic_matched_via(
    rule: dict,
    patient_age: float | None,
) -> list[dict[str, Any]]:
    if patient_age is None:
        return []
    out: list[dict[str, Any]] = []
    for constraint in rule.get("applies_to") or []:
        if constraint.get("concept_id") != _AGE_CONCEPT_ID:
            continue
        out.append(
            {
                "kind": "DEMOGRAPHIC",
                "field": "age",
                "operator": constraint.get("operator") or ">=",
                "value": constraint.get("value"),
                "unit": "years",
                "patient_value": patient_age,
            }
        )
    return out


def _format_match(
    rule: dict,
    *,
    matched_via: list[dict[str, Any]] | None = None,
    unverified_qualifiers: list[str] | None = None,
    patient_codes: list[str] | None = None,
    observations: list[dict[str, Any]] | None = None,
) -> dict:
    """Format a matched rule for the API response.

    ``matched_via`` (DI-LEO-AI-510) lists every satisfied leaf on the firing
    branch: demographics, SNOMED concepts, observations, medications,
    allergies, treatment history, and nested rule references.
    """
    payload = {
        "rule_id": rule["rule_id"],
        "name": rule.get("name"),
        "strength": rule.get("strength"),
        "guideline_id": rule.get("guideline_id"),
        "guideline_title": rule.get("guideline_title"),
        "guideline_publisher": rule.get("guideline_publisher"),
        "guideline_source": rule.get("guideline_source"),
        "chapter_title": rule.get("chapter_title"),
        "recommendation_verbatim": rule.get("recommendation_verbatim"),
        # "action" (singular) is a one-release back-compat shim equal to
        # actions[0] -- see guideline_compiler.py's Action metadata note.
        "action": rule.get("action"),
        "actions": rule.get("actions") or [],
        "confidence": 1.0,
    }
    if matched_via:
        payload["matched_via"] = matched_via
    if unverified_qualifiers:
        payload["unverified_qualifiers"] = [
            kind for kind in unverified_qualifiers if kind
        ]
    policy = rule.get("investigation_policy")
    if policy:
        from libs.guidelines.soft_qualifier import fit_is_present, status_for_policy

        payload["investigation_status"] = status_for_policy(
            policy, fit_is_present(patient_codes, observations)
        )
    return payload


def _check_pds_gender_gate(
    patient_sex: str | None,
) -> tuple[bool, str | None, str | None]:
    """Return (requires_review, reason, limitation_notice) for PDS gender.

    Implements DI-9AA2CDA5 clauses (a) and (b): flag when PDS gender is
    unusable (other/unknown); warn when it is assumptive (male/female).
    """
    if not patient_sex:
        return False, None, None
    normalised = patient_sex.lower().strip()
    if normalised in _PDS_UNUSABLE_SEX:
        return True, "pds_gender_unusable", None
    if normalised in _SEX_CODE:
        return False, None, _LIMITATION_NOTICE
    return False, None, None


def _check_anatomy_conflict(
    patient_codes: list[str],
    patient_sex: str | None,
) -> bool:
    """Return True when patient_codes contain anatomy that conflicts with PDS gender.

    Implements DI-9AA2CDA5 clause (c): a male-recorded patient with female
    reproductive anatomy codes (or vice versa) indicates a conflict that the
    clinician must review.  Returns False when no anatomy codes are present
    (clause d -- no inference from PDS gender alone).
    """
    if not patient_sex:
        return False
    normalised = patient_sex.lower().strip()
    code_set = set(patient_codes)
    if normalised in {"male", "m"}:
        return bool(code_set & _FEMALE_ANATOMY_SNOMED)
    if normalised in {"female", "f"}:
        return bool(code_set & _MALE_ANATOMY_SNOMED)
    return False


def _tree_has_sex_node(node: dict[str, Any] | None) -> bool:
    """Return True when the logic tree contains a DEMOGRAPHIC sex node."""
    if not node:
        return False
    if str(node.get("kind") or "").upper() == "DEMOGRAPHIC":
        return str(node.get("field") or "").lower() == "sex"
    return any(_tree_has_sex_node(c) for c in (node.get("children") or []))


def _count_sex_sensitive_rules(rules: list[dict]) -> int:
    """Count rules that have a DEMOGRAPHIC sex node in their logic tree."""
    return sum(1 for r in rules if _tree_has_sex_node(r.get("logic_tree")))


def _not_compiled_response(
    scope_type: str | None,
    scope_id: str | None,
) -> dict[str, Any]:
    """Build the standard response when no ruleset has been compiled."""
    st = scope_type or "global"
    si = scope_id or "default"
    return {
        "matched_rules": [],
        "active_version": None,
        "not_compiled": True,
        "message": "No active ruleset compiled yet.",
        "recompile_hint": (
            f"POST /terminology/guidelines/bitmap/compile "
            f"with scope_type={st} scope_id={si}"
        ),
        "scope_type": st,
        "scope_id": si,
        "gender_review_flag": False,
        "gender_review_reason": None,
        "limitation_notice": None,
        "gender_basis": None,
        "gender_sensitive_rules_skipped": 0,
    }


def _prefetch_rule_caches(
    rules: list[dict],
    store: BitmapStore,
) -> tuple[dict[str, BitMap], dict[str, int]]:
    """Return bulk-fetched bitmap and int_id caches for all rules.

    Pre-fetches all CONCEPT-node bitmaps and synonym seed int_ids in two
    round trips (MGET + HMGET) instead of one per node, reducing Redis
    latency for rulesets with many CONCEPT leaves.
    """
    all_bitmap_ids: list[str] = []
    all_seed_ids: list[str] = []
    for rule in rules:
        tree = rule.get("logic_tree")
        if tree:
            all_bitmap_ids.extend(_collect_tree_bitmap_ids(tree))
            all_seed_ids.extend(_collect_tree_seed_ids(tree))
        for group in (rule.get("criteria_groups") or []):
            bid = group.get("bitmap_id")
            if bid:
                all_bitmap_ids.append(bid)
    return (
        store.get_bitmaps_bulk(list(set(all_bitmap_ids))),
        store.get_int_ids_bulk(list(set(all_seed_ids))),
    )
