"""SiteRulebook schema, JSON round-trip, RulebookBundle, validate_no_pii.

Atlas trace:
  DI: DI-951F26E0 (schema + validator)
  DI: DI-FA3CE229 (RulebookBundle is the runtime bundle type)
  Mitigates: R-192A2D18 (PII leakage), R-5FA0C950 (cross-site leakage),
             R-098701D8 (version skew)

Design rules:
- Rulebooks are pure data. No patient id, encounter id, date, NHS
  number, or raw clinical text is ever permitted in a rulebook.
- validate_no_pii is the hard gate enforced by the registry before any
  write to the Knowledge Graph. A contaminated rulebook never reaches a
  customer instance.
- Schema version is semver; loading a rulebook whose schema_version is
  outside SUPPORTED_SCHEMA_RANGE raises RulebookSchemaVersionError.
- Bundles are frozen after construction so signal extractors cannot
  mutate them across requests.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

SCHEMA_VERSION = "1.0.0"
SUPPORTED_SCHEMA_RANGE: tuple[str, str] = ("1.0.0", "1.0.0")


class RulebookPiiError(ValueError):
    """Raised when a rulebook contains a string that looks like PII."""


class RulebookSchemaVersionError(ValueError):
    """Raised when a rulebook's schema_version is outside the supported range."""


@dataclass(frozen=True)
class Activation:
    auto_publish: bool = False
    suggest: bool = False
    min_precision: float = 0.95


@dataclass(frozen=True)
class Windows:
    lookback_days: int = 365
    lookahead_days: int = 730


@dataclass(frozen=True)
class TierThresholds:
    auto_votes: int = 2
    suggest_votes: int = 2
    diversity_required_for_auto: int = 2


@dataclass(frozen=True)
class ScorerWeights:
    code: float = 1.0
    text: float = 0.4
    pathway: float = 0.8
    result: float = 0.9
    treatment: float = 0.6
    bias: float = -0.2


@dataclass(frozen=True)
class Anchors:
    referral_snomed: tuple[str, ...] = ()
    clinic_seen_snomed: tuple[str, ...] = ()
    suspected_snomed: tuple[str, ...] = ()
    confirmed_snomed: tuple[str, ...] = ()


@dataclass(frozen=True)
class CodeChannel:
    suspected_snomed: tuple[str, ...] = ()
    confirmed_snomed: tuple[str, ...] = ()
    benign_closure_snomed: tuple[str, ...] = ()
    suspected_confidence: float = 0.70
    confirmed_confidence: float = 0.85
    benign_closure_confidence: float = 0.70


@dataclass(frozen=True)
class ResultChannel:
    observation_snomed: tuple[str, ...] = ()
    investigation_terms: tuple[str, ...] = ()
    positive_terms: tuple[str, ...] = ()
    negative_terms: tuple[str, ...] = ()


# Canonical context-tier milestone tags that rulebooks may enumerate
# regex patterns for. Mirrors CONTEXT_MILESTONE_TYPES on the
# analysis_worker side (services/analysis_worker/app/episode_engine/
# schemas.py) and on the analytics API side
# (services/analytics_api/app/routers/_episode_crud_helpers.py).
# DI-2C015ADE (supersedes DI-50C7E89C).
CONTEXT_MILESTONE_TAGS: tuple[str, ...] = (
    "related_gp_visit",
    "primary_care_investigations",
    "referral_admin",
    "referral_sent",
    "related_specialist_visit",
    "specialist_diagnostics",
    "related_correspondence",
)


@dataclass(frozen=True)
class TextChannel:
    regex_catalogue: tuple[str, ...] = ()
    # Per-context-tag regex catalogue. Keys are from
    # CONTEXT_MILESTONE_TAGS; values are tuples of case-insensitive
    # regex strings. Used by the text_channel extractor to emit
    # role="context_milestone" signals that the episode_engine fuses
    # with its LLM-emitted context milestones before writing to
    # Neo4j.
    #
    # Empty by default so rulebooks that have not been authored yet
    # simply contribute no context signals (fail-safe).
    context_role_catalogue: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )


@dataclass(frozen=True)
class TreatmentChannel:
    snomed: tuple[str, ...] = ()
    regex_catalogue: tuple[str, ...] = ()


@dataclass(frozen=True)
class PathwayChannel:
    form_types: tuple[str, ...] = ()
    reason_regex: tuple[str, ...] = ()


@dataclass(frozen=True)
class Signals:
    code_channel: CodeChannel = field(default_factory=CodeChannel)
    text_channel: TextChannel = field(default_factory=TextChannel)
    pathway_channel: PathwayChannel = field(default_factory=PathwayChannel)
    result_channel: ResultChannel = field(default_factory=ResultChannel)
    treatment_channel: TreatmentChannel = field(default_factory=TreatmentChannel)


@dataclass(frozen=True)
class ClosureRule:
    requires_any_of: tuple[str, ...] = ()
    and_no_confirmed_within_days: int | None = None


@dataclass(frozen=True)
class Closure:
    benign: ClosureRule = field(default_factory=ClosureRule)
    completed: ClosureRule = field(default_factory=ClosureRule)
    use_core_closure_set: bool = True


@dataclass(frozen=True)
class SiteRulebook:
    """Portable per-site rulebook artefact.

    Pure data - no patient id, encounter id, date, or raw text. The
    registry enforces this via validate_no_pii before any write.
    """

    site_key: str
    rulebook_version: str
    schema_version: str = SCHEMA_VERSION
    dependencies: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({})
    )
    activation: Activation = field(default_factory=Activation)
    windows: Windows = field(default_factory=Windows)
    tier_thresholds: TierThresholds = field(default_factory=TierThresholds)
    scorer_weights: ScorerWeights = field(default_factory=ScorerWeights)
    anchors: Anchors = field(default_factory=Anchors)
    signals: Signals = field(default_factory=Signals)
    closure: Closure = field(default_factory=Closure)
    cross_site_guard: tuple[str, ...] = ()

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(_to_plain(self), indent=indent, sort_keys=True)

    @classmethod
    def from_json(cls, blob: str) -> "SiteRulebook":
        data = json.loads(blob)
        return from_mapping(data)


def from_mapping(data: Mapping[str, Any]) -> SiteRulebook:
    """Build a SiteRulebook from a plain mapping (already-parsed JSON)."""

    schema = str(data.get("schema_version") or SCHEMA_VERSION)
    if not _schema_supported(schema):
        lo, hi = SUPPORTED_SCHEMA_RANGE
        raise RulebookSchemaVersionError(
            f"rulebook schema_version {schema!r} outside supported range "
            f"[{lo}, {hi}]"
        )
    return SiteRulebook(
        site_key=str(data["site_key"]),
        rulebook_version=str(data["rulebook_version"]),
        schema_version=schema,
        dependencies=MappingProxyType(dict(data.get("dependencies") or {})),
        activation=_build_activation(data.get("activation") or {}),
        windows=_build_windows(data.get("windows") or {}),
        tier_thresholds=_build_tier(data.get("tier_thresholds") or {}),
        scorer_weights=_build_weights(data.get("scorer_weights") or {}),
        anchors=_build_anchors(data.get("anchors") or {}),
        signals=_build_signals(data.get("signals") or {}),
        closure=_build_closure(data.get("closure") or {}),
        cross_site_guard=_tuple_of_str(data.get("cross_site_guard")),
    )


@dataclass(frozen=True)
class RulebookBundle:
    """Immutable per-process view of the current champion rulebook for
    every site. Signal extractors, boundary detector and scorer read
    from this bundle instead of module-level constants.
    """

    sites: Mapping[str, SiteRulebook] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def get(self, site_key: str) -> SiteRulebook | None:
        return self.sites.get((site_key or "").strip().lower())

    def get_or_disabled(self, site_key: str) -> SiteRulebook:
        """Return the champion rulebook for the site, or a fail-safe
        disabled rulebook if no champion is registered. The disabled
        rulebook has activation.auto_publish=False and
        activation.suggest=False so the detector returns nothing for
        that site until a champion is promoted.
        """

        rb = self.get(site_key)
        if rb is not None:
            return rb
        return SiteRulebook(
            site_key=(site_key or "").strip().lower(),
            rulebook_version="0.0.0-disabled",
            activation=Activation(auto_publish=False, suggest=False),
        )


# ----------------------------------------------------------------------
# validate_no_pii
# ----------------------------------------------------------------------

# 7+ consecutive digits catches NHS numbers (10), MRNs (7-9), encounter
# ids like 4920262426, and any raw identifier-shaped run. We allow the
# SNOMED concept-id fields to contain digit runs but enforce per-field
# category checks in _iter_text_fields.
_DIGIT_RUN = re.compile(r"\d{7,}")
_DATE_LIKE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_PII_MARKERS = re.compile(
    r"\b(nhs\s?number|mrn|patient\s?id|hospital\s?number)\b",
    re.IGNORECASE,
)
# Conservative free-text bound: a regex/term longer than 200 chars is
# almost certainly a copied note fragment, not a pattern.
_MAX_TEXT_LEN = 200


def validate_no_pii(rb: SiteRulebook) -> None:
    """Raise RulebookPiiError if any text field contains PII-shaped content.

    Fields holding SNOMED concept ids are whitelisted for digit runs;
    everything else (terms, regex patterns, citations) is scanned.
    """

    for field_path, value in _iter_free_text(rb):
        _check_no_pii(field_path, value)
    for field_path, value in _iter_snomed_fields(rb):
        _check_snomed_shape(field_path, value)


def _iter_free_text(rb: SiteRulebook) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    out.extend(
        (f"signals.result_channel.investigation_terms[{i}]", v)
        for i, v in enumerate(rb.signals.result_channel.investigation_terms)
    )
    out.extend(
        (f"signals.result_channel.positive_terms[{i}]", v)
        for i, v in enumerate(rb.signals.result_channel.positive_terms)
    )
    out.extend(
        (f"signals.result_channel.negative_terms[{i}]", v)
        for i, v in enumerate(rb.signals.result_channel.negative_terms)
    )
    out.extend(
        (f"signals.text_channel.regex_catalogue[{i}]", v)
        for i, v in enumerate(rb.signals.text_channel.regex_catalogue)
    )
    for tag, patterns in rb.signals.text_channel.context_role_catalogue.items():
        out.append(
            (
                f"signals.text_channel.context_role_catalogue.{tag}.key",
                str(tag),
            )
        )
        for i, v in enumerate(patterns):
            out.append(
                (
                    "signals.text_channel.context_role_catalogue." f"{tag}[{i}]",
                    v,
                )
            )
    out.extend(
        (f"signals.treatment_channel.regex_catalogue[{i}]", v)
        for i, v in enumerate(rb.signals.treatment_channel.regex_catalogue)
    )
    out.extend(
        (f"signals.pathway_channel.form_types[{i}]", v)
        for i, v in enumerate(rb.signals.pathway_channel.form_types)
    )
    out.extend(
        (f"signals.pathway_channel.reason_regex[{i}]", v)
        for i, v in enumerate(rb.signals.pathway_channel.reason_regex)
    )
    out.append(("rulebook_version", rb.rulebook_version))
    out.append(("site_key", rb.site_key))
    for k, v in rb.dependencies.items():
        out.append((f"dependencies.{k}", str(v)))
    return out


def _iter_snomed_fields(rb: SiteRulebook) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for fld in (
        "referral_snomed",
        "clinic_seen_snomed",
        "suspected_snomed",
        "confirmed_snomed",
    ):
        values = getattr(rb.anchors, fld)
        out.extend((f"anchors.{fld}[{i}]", v) for i, v in enumerate(values))
    for fld in ("suspected_snomed", "confirmed_snomed", "benign_closure_snomed"):
        values = getattr(rb.signals.code_channel, fld)
        out.extend(
            (f"signals.code_channel.{fld}[{i}]", v) for i, v in enumerate(values)
        )
    values = rb.signals.result_channel.observation_snomed
    out.extend(
        (f"signals.result_channel.observation_snomed[{i}]", v)
        for i, v in enumerate(values)
    )
    values = rb.signals.treatment_channel.snomed
    out.extend(
        (f"signals.treatment_channel.snomed[{i}]", v) for i, v in enumerate(values)
    )
    out.extend((f"cross_site_guard[{i}]", v) for i, v in enumerate(rb.cross_site_guard))
    for rule_name in ("benign", "completed"):
        rule: ClosureRule = getattr(rb.closure, rule_name)
        for i, v in enumerate(rule.requires_any_of):
            out.append((f"closure.{rule_name}.requires_any_of[{i}]", v))
    return out


def _check_no_pii(path: str, value: str) -> None:
    if not isinstance(value, str):
        return
    if len(value) > _MAX_TEXT_LEN:
        raise RulebookPiiError(
            f"{path}: string exceeds {_MAX_TEXT_LEN} chars "
            f"(possible copied clinical text)"
        )
    if _DIGIT_RUN.search(value):
        raise RulebookPiiError(f"{path}: contains a 7+ digit run (possible identifier)")
    if _DATE_LIKE.search(value):
        raise RulebookPiiError(
            f"{path}: contains a YYYY-MM-DD date (possible real encounter date)"
        )
    if _PII_MARKERS.search(value):
        raise RulebookPiiError(
            f"{path}: contains an identifier marker (NHS number / MRN / etc)"
        )


def _check_snomed_shape(path: str, value: str) -> None:
    if not isinstance(value, str):
        raise RulebookPiiError(f"{path}: SNOMED entry is not a string")
    stripped = value.strip()
    # SNOMED concept ids: 6-18 digits (NHS England bounds are generous).
    # Prefix strings like 'snomed:' are also acceptable and common in
    # closure rules that cite a concept id.
    if stripped.startswith("snomed:"):
        stripped = stripped[len("snomed:") :]
    if not stripped.isdigit():
        # String references like 'result.negative_terms' are allowed in
        # closure.requires_any_of; only reject if it contains free text
        # that could carry PII.
        _check_no_pii(path, value)
        return
    if len(stripped) < 6 or len(stripped) > 18:
        raise RulebookPiiError(
            f"{path}: SNOMED-shaped digits outside 6-18 range " f"(possible identifier)"
        )


# ----------------------------------------------------------------------
# JSON serialisation helpers
# ----------------------------------------------------------------------


def _to_plain(rb: SiteRulebook) -> dict[str, Any]:
    return {
        "site_key": rb.site_key,
        "rulebook_version": rb.rulebook_version,
        "schema_version": rb.schema_version,
        "dependencies": dict(rb.dependencies),
        "activation": {
            "auto_publish": rb.activation.auto_publish,
            "suggest": rb.activation.suggest,
            "min_precision": rb.activation.min_precision,
        },
        "windows": {
            "lookback_days": rb.windows.lookback_days,
            "lookahead_days": rb.windows.lookahead_days,
        },
        "tier_thresholds": {
            "auto_votes": rb.tier_thresholds.auto_votes,
            "suggest_votes": rb.tier_thresholds.suggest_votes,
            "diversity_required_for_auto": (
                rb.tier_thresholds.diversity_required_for_auto
            ),
        },
        "scorer_weights": {
            "code": rb.scorer_weights.code,
            "text": rb.scorer_weights.text,
            "pathway": rb.scorer_weights.pathway,
            "result": rb.scorer_weights.result,
            "treatment": rb.scorer_weights.treatment,
            "bias": rb.scorer_weights.bias,
        },
        "anchors": {
            "referral_snomed": list(rb.anchors.referral_snomed),
            "clinic_seen_snomed": list(rb.anchors.clinic_seen_snomed),
            "suspected_snomed": list(rb.anchors.suspected_snomed),
            "confirmed_snomed": list(rb.anchors.confirmed_snomed),
        },
        "signals": {
            "code_channel": {
                "suspected_snomed": list(rb.signals.code_channel.suspected_snomed),
                "confirmed_snomed": list(rb.signals.code_channel.confirmed_snomed),
                "benign_closure_snomed": list(
                    rb.signals.code_channel.benign_closure_snomed
                ),
                "suspected_confidence": (rb.signals.code_channel.suspected_confidence),
                "confirmed_confidence": (rb.signals.code_channel.confirmed_confidence),
                "benign_closure_confidence": (
                    rb.signals.code_channel.benign_closure_confidence
                ),
            },
            "text_channel": {
                "regex_catalogue": list(rb.signals.text_channel.regex_catalogue),
                "context_role_catalogue": {
                    tag: list(patterns)
                    for tag, patterns in (
                        rb.signals.text_channel.context_role_catalogue.items()
                    )
                },
            },
            "pathway_channel": {
                "form_types": list(rb.signals.pathway_channel.form_types),
                "reason_regex": list(rb.signals.pathway_channel.reason_regex),
            },
            "result_channel": {
                "observation_snomed": list(
                    rb.signals.result_channel.observation_snomed
                ),
                "investigation_terms": list(
                    rb.signals.result_channel.investigation_terms
                ),
                "positive_terms": list(rb.signals.result_channel.positive_terms),
                "negative_terms": list(rb.signals.result_channel.negative_terms),
            },
            "treatment_channel": {
                "snomed": list(rb.signals.treatment_channel.snomed),
                "regex_catalogue": list(rb.signals.treatment_channel.regex_catalogue),
            },
        },
        "closure": {
            "benign": {
                "requires_any_of": list(rb.closure.benign.requires_any_of),
                "and_no_confirmed_within_days": (
                    rb.closure.benign.and_no_confirmed_within_days
                ),
            },
            "completed": {
                "requires_any_of": list(rb.closure.completed.requires_any_of),
                "and_no_confirmed_within_days": (
                    rb.closure.completed.and_no_confirmed_within_days
                ),
            },
            "use_core_closure_set": rb.closure.use_core_closure_set,
        },
        "cross_site_guard": list(rb.cross_site_guard),
    }


def _tuple_of_str(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(str(v) for v in value)


def _build_context_role_catalogue(
    raw: Any,
) -> Mapping[str, tuple[str, ...]]:
    """Return an immutable {context_tag: tuple[regex, ...]} mapping.

    Unknown keys are silently dropped so an older rulebook that
    carries experimental tags cannot sneak a non-canonical tag into
    the runtime. Canonical tags that are absent map to ``()``.
    """
    if not raw or not isinstance(raw, Mapping):
        return MappingProxyType({})
    out: dict[str, tuple[str, ...]] = {}
    for tag in CONTEXT_MILESTONE_TAGS:
        entries = raw.get(tag)
        if not entries:
            continue
        patterns = _tuple_of_str(entries)
        if patterns:
            out[tag] = patterns
    return MappingProxyType(out)


def _build_activation(data: Mapping[str, Any]) -> Activation:
    return Activation(
        auto_publish=bool(data.get("auto_publish", False)),
        suggest=bool(data.get("suggest", False)),
        min_precision=float(data.get("min_precision", 0.95)),
    )


def _build_windows(data: Mapping[str, Any]) -> Windows:
    return Windows(
        lookback_days=int(data.get("lookback_days", 365)),
        lookahead_days=int(data.get("lookahead_days", 730)),
    )


def _build_tier(data: Mapping[str, Any]) -> TierThresholds:
    return TierThresholds(
        auto_votes=int(data.get("auto_votes", 2)),
        suggest_votes=int(data.get("suggest_votes", 2)),
        diversity_required_for_auto=int(data.get("diversity_required_for_auto", 2)),
    )


def _build_weights(data: Mapping[str, Any]) -> ScorerWeights:
    return ScorerWeights(
        code=float(data.get("code", 1.0)),
        text=float(data.get("text", 0.4)),
        pathway=float(data.get("pathway", 0.8)),
        result=float(data.get("result", 0.9)),
        treatment=float(data.get("treatment", 0.6)),
        bias=float(data.get("bias", -0.2)),
    )


def _build_anchors(data: Mapping[str, Any]) -> Anchors:
    return Anchors(
        referral_snomed=_tuple_of_str(data.get("referral_snomed")),
        clinic_seen_snomed=_tuple_of_str(data.get("clinic_seen_snomed")),
        suspected_snomed=_tuple_of_str(data.get("suspected_snomed")),
        confirmed_snomed=_tuple_of_str(data.get("confirmed_snomed")),
    )


def _build_signals(data: Mapping[str, Any]) -> Signals:
    code = data.get("code_channel") or {}
    return Signals(
        code_channel=CodeChannel(
            suspected_snomed=_tuple_of_str(code.get("suspected_snomed")),
            confirmed_snomed=_tuple_of_str(code.get("confirmed_snomed")),
            benign_closure_snomed=_tuple_of_str(code.get("benign_closure_snomed")),
            suspected_confidence=float(code.get("suspected_confidence", 0.70)),
            confirmed_confidence=float(code.get("confirmed_confidence", 0.85)),
            benign_closure_confidence=float(
                code.get("benign_closure_confidence", 0.70)
            ),
        ),
        text_channel=TextChannel(
            regex_catalogue=_tuple_of_str(
                (data.get("text_channel") or {}).get("regex_catalogue")
            ),
            context_role_catalogue=_build_context_role_catalogue(
                (data.get("text_channel") or {}).get("context_role_catalogue")
            ),
        ),
        pathway_channel=PathwayChannel(
            form_types=_tuple_of_str(
                (data.get("pathway_channel") or {}).get("form_types")
            ),
            reason_regex=_tuple_of_str(
                (data.get("pathway_channel") or {}).get("reason_regex")
            ),
        ),
        result_channel=ResultChannel(
            observation_snomed=_tuple_of_str(
                (data.get("result_channel") or {}).get("observation_snomed")
            ),
            investigation_terms=_tuple_of_str(
                (data.get("result_channel") or {}).get("investigation_terms")
            ),
            positive_terms=_tuple_of_str(
                (data.get("result_channel") or {}).get("positive_terms")
            ),
            negative_terms=_tuple_of_str(
                (data.get("result_channel") or {}).get("negative_terms")
            ),
        ),
        treatment_channel=TreatmentChannel(
            snomed=_tuple_of_str((data.get("treatment_channel") or {}).get("snomed")),
            regex_catalogue=_tuple_of_str(
                (data.get("treatment_channel") or {}).get("regex_catalogue")
            ),
        ),
    )


def _build_closure(data: Mapping[str, Any]) -> Closure:
    return Closure(
        benign=_build_rule(data.get("benign") or {}),
        completed=_build_rule(data.get("completed") or {}),
        use_core_closure_set=bool(data.get("use_core_closure_set", True)),
    )


def _build_rule(data: Mapping[str, Any]) -> ClosureRule:
    return ClosureRule(
        requires_any_of=_tuple_of_str(data.get("requires_any_of")),
        and_no_confirmed_within_days=data.get("and_no_confirmed_within_days"),
    )


def _schema_supported(schema: str) -> bool:
    lo, hi = SUPPORTED_SCHEMA_RANGE
    return _parse_semver(lo) <= _parse_semver(schema) <= _parse_semver(hi)


def _parse_semver(value: str) -> tuple[int, int, int]:
    parts = (value or "").split("-", 1)[0].split(".")
    nums: list[int] = []
    for p in parts[:3]:
        try:
            nums.append(int(p))
        except ValueError:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    return nums[0], nums[1], nums[2]
