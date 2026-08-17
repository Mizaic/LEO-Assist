"""Shared dataclass types for the configurable NER guard rule infrastructure.

Atlas trace:
  DO: DO-F20DE29D
  DI: DI-34712A9A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-F20DE29D")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class PipelineRuleBase:
    """Base type for all configurable NER guard rules.

    All guard rule subtypes extend this. Fields map directly to the
    :NerGuardRule Neo4j node properties and the JSON seed file format.

    source: "builtin" -- loaded from seed JSON shipped with the code.
            "custom"  -- added or overridden by a platform admin / tenant.
    """

    rule_id: str = ""
    active: bool = True
    org_id: str | None = None
    plan_definition_id: str | None = None
    priority: int = 10
    created_by: str = ""
    created_at: str = ""
    source: Literal["builtin", "custom"] = "builtin"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SituationLookupRule(PipelineRuleBase):
    """A single configurable situation-lookup normalisation rule.

    Replaces a hardcoded entry in _SITUATION_NORMALIZATIONS.
    pattern: Python regex string matched against the entity text (re.IGNORECASE).
    canonical: SNOMED-friendly lookup term to substitute, or None to pass through.
    """

    pattern: str = ""
    canonical: str | None = None


@dataclass
class TermConceptBlocklistRule(PipelineRuleBase):
    """A configurable blocklist entry: suppress specific SNOMED codes for a surface form.

    Replaces a hardcoded entry in _TERM_CONCEPT_BLOCKLIST in terminology.py.
    surface_form: the normalised entity text to match (case-insensitive exact match).
    blocked_concept_ids: SNOMED concept IDs to suppress when the surface matches.
    """

    surface_form: str = ""
    blocked_concept_ids: list[str] = field(default_factory=list)


@dataclass
class LabValueGuardRule(PipelineRuleBase):
    """A configurable extension to the lab value guard.

    Adds a new lab test pattern to the guard's regex alternation so the
    guard suppresses disorders inferred from that test without a code change.
    pattern: Python regex fragment to add to the lab test alternation (no IGNORECASE needed).
    suppressed_disorders: optional list of disorder terms whose suppression is
                          triggered when this lab test appears in a lab sentence.
    """

    pattern: str = ""
    suppressed_disorders: list[str] = field(default_factory=list)


@dataclass
class ReferralRoutingGuardRule(PipelineRuleBase):
    """A configurable extension to the referral routing guard.

    Adds a new pattern to one of the routing guard regex groups so that
    new investigation types or cancer sites can be recognised without a
    code change.
    pattern_type: which regex group to extend.
      "named_test"  -- add to _NAMED_TEST_RE (span contains a named test -> keep)
      "site"        -- add to _SITE alternation (cancer site -> keep)
      "keep_action" -- add to _KEEP_ACTION_RE (clinical action -> keep)
    pattern: Python regex fragment to add to the selected group.
    """

    pattern: str = ""
    pattern_type: str = "named_test"


@dataclass
class AssertionGuardRule(PipelineRuleBase):
    """A configurable extension to the assertion guards in post_processing.

    Allows platform admins to add SNOMED concept IDs that should always
    keep assertion=present (lifestyle / status concepts that encode polarity
    in their preferred term).

    rule_type: "lifestyle_concept" -- concept_id that should be restored to
               present when ConText marks it absent, because the SNOMED term
               itself encodes the status (e.g. Ex-smoker, Non-drinker).
    concept_id: SNOMED concept ID string (digits only, no leading zeros).
    """

    rule_type: str = "lifestyle_concept"
    concept_id: str = ""


@dataclass
class ScopeGuardRule(PipelineRuleBase):
    """A configurable extension to the scope guard in scope_guard.py.

    Allows platform admins to add safety-netting or recommendation phrases
    without a code change.

    rule_type: "safety_netting" -- pattern added to _SAFETY_NETTING_RE
               "recommendation" -- pattern added to _RECOMMENDATION_RE
    pattern: Python regex fragment to add to the relevant alternation.
    """

    rule_type: str = "safety_netting"
    pattern: str = ""


@dataclass
class EntityTypeNormRule(PipelineRuleBase):
    """A configurable extension to entity-type normalisation in post_processing.

    Allows platform admins to add custom text strings to the built-in
    episode-marker or severity-modifier lookup sets without a code change.

    rule_type: "episode_marker" -- lowercased text that should reclassify an
               X_TEMPORAL or X_PATHWAY_MILESTONE entity to qualifier_value.
               "severity_modifier" -- lowercased text that should reclassify
               an attribute or finding entity to qualifier_value.
    text: the exact lowercased surface text to match.
    """

    rule_type: str = "episode_marker"
    text: str = ""


@dataclass
class CheckboxNormRule(PipelineRuleBase):
    """A configurable extension to the checkbox normaliser in form_checkbox_normalizer.py.

    Allows platform admins to add form-specific question patterns that should
    be suppressed (marked NON_EXTRACTABLE) without a code change.

    rule_type: "admin_question" -- pattern added to _ADMIN_QUESTION regex so
               matching lines are treated as admin questions and suppressed.
    pattern: Python regex fragment (re.IGNORECASE applied; anchor with ^\\s* as needed).
    """

    rule_type: str = "admin_question"
    pattern: str = ""


@dataclass
class BodyStructureGuardRule(PipelineRuleBase):
    """Keep a body-part span as a site, or always keep a reproductive organ.

    rule_type: "always_keep" -- reproductive organ id or name (gender check).
               "keep_as_site" -- extra body part kept when used as a site.
               "drop_orphan" -- drop keep-as-site spans with no finding_site.
    pattern: SNOMED id, regex fragment, or true/false for drop_orphan.
    """

    rule_type: str = "keep_as_site"
    pattern: str = ""


@dataclass
class FactLinkGuardRule(PipelineRuleBase):
    """Allow a relation type at runtime without a code change.

    rule_type: "allowed_relation" -- pattern is the relation type name.
    """

    rule_type: str = "allowed_relation"
    pattern: str = ""
