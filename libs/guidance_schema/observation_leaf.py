"""Pydantic wire shape for the OBSERVATION leaf in a logic tree.

Atlas trace (Phase 5a):
    UN: UN-26E57FA1
    DI: DI-7790EEA5
    DO: DO-710270EF
    Risk: R-555C8691
    VT: VT-404C1E2C

The OBSERVATION leaf lets a rule ask a question about a numeric clinical
observation on a patient (for example "platelet count >= 400 x10^9/L in
the last year"). It is intentionally separate from the CONCEPT leaf so:

  - CONCEPT keeps the simple "is this code present on the patient?"
    bitmap-set semantics it has today.
  - OBSERVATION carries the comparison operator, the threshold value,
    the unit, the recency window, and the aggregation / temporal /
    reference-range / trend mode the rule is asking about.

Five evaluation modes are supported in v1. Each maps to a distinct
clinical question; they are mutually exclusive within a single leaf:

  ABSOLUTE       Compare the most-recent reading inside ``within_days``
                 against ``value`` using ``operator``. The default mode.
                 Fails closed when no reading exists in the window.

  TEMPORAL       Look for ``temporal.count`` consecutive readings within
                 ``within_days`` that all satisfy operator/value, where
                 each consecutive pair is at least
                 ``temporal.interval_min_days`` and at most
                 ``temporal.interval_max_days`` apart. Used for "two
                 PSAs > 4, at least six months apart" patterns.

  REFERENCE_RANGE
                 Compare the most-recent reading against the patient's
                 reference range (upper or lower limit), optionally
                 multiplied by ``reference_range.multiple_of_range``.
                 The reference range comes from a per-observable,
                 per-sex, per-age-band lookup table -- when no range
                 is found for the patient, fails closed.

  TREND          Compare the change in value across ``trend.window_days``.
                 ``trend.delta_kind = absolute`` measures (latest - oldest);
                 ``trend.delta_kind = percent`` measures
                 100 * (latest - oldest) / max(abs(oldest), epsilon).
                 Comparison uses operator/value as usual. Fails closed
                 when fewer than two readings sit inside the window.

  AGGREGATE      Compute aggregation.kind ("mean" | "median" | "min" |
                 "max") over the last ``aggregation.lookback_n``
                 readings inside ``within_days``, then compare against
                 operator/value. Fails closed when fewer than
                 ``aggregation.lookback_n`` readings exist.

Common rules across all five modes:

  - ``operator`` must be one of >=, <=, >, <, =, between.
  - ``between`` requires ``value`` to be a ``[low, high]`` tuple where
    low <= high. Every other operator requires a scalar ``value``.
  - ``unit`` must be the canonical unit registered for ``observable_id``
    in libs.units.observable_units, OR a unit that converts cleanly to
    the canonical unit. The compiler refuses to compile a leaf whose
    unit cannot be reconciled.
  - Missing data ALWAYS fails closed (rule does not fire). This matches
    today's behaviour for unrecognised demographic gates and is the
    safe default for clinical decision support.
  - Exactly one of ``temporal``, ``reference_range``, ``trend``,
    ``aggregation`` may be set; if all four are absent the leaf
    operates in ABSOLUTE mode.

The leaf does NOT carry the patient's actual readings -- those flow in
through the EvaluateRequest payload. The leaf describes only the
question being asked, not the answer.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# Operators supported across every mode.
ComparisonOperator = Literal[">=", "<=", ">", "<", "=", "between"]

# Aggregation functions that may be applied across the lookback window.
AggregationFunction = Literal["mean", "median", "min", "max"]

# Trend-delta semantics. ``absolute`` is (latest - oldest); ``percent``
# is 100 * (latest - oldest) / max(abs(oldest), 1e-9). Percent is
# clinically more common for renal / weight / haematology trends.
DeltaKind = Literal["absolute", "percent"]

# Which reference-range bound the leaf is comparing against. ``upper``
# is the upper limit of normal (e.g. ULN for ALT); ``lower`` is the
# lower limit (e.g. LLN for haemoglobin).
ReferenceRangeBound = Literal["upper", "lower"]


# Bounds chosen so a rule cannot accidentally ask about timescales the
# evaluator cannot support. 7300 days = 20 years; pragmatically every
# clinically meaningful recency window fits inside that. ``within_days``
# default of 365 matches NICE's "in the last year" wording.
_MIN_WINDOW_DAYS = 1
_MAX_WINDOW_DAYS = 7300

# Aggregation lookback bounds. 1 = "the last reading" (degenerate case);
# 50 leaves headroom for trend rules over long observation histories
# while still letting the evaluator cap the bundle it has to fetch.
_MIN_LOOKBACK_N = 1
_MAX_LOOKBACK_N = 50

# Temporal interval bounds. Lower bound 1 day stops "two readings the
# same day at least 0 days apart" trivial matches; upper bound matches
# the recency window cap.
_MIN_INTERVAL_DAYS = 1


class ObservationLeafValidationError(ValueError):
    """Raised when an OBSERVATION leaf payload is structurally invalid.

    Subclassed from ValueError so FastAPI's request validation surfaces
    the message in the standard error envelope, and so callers that
    already catch ValueError on logic-tree validation keep working.
    """


class TemporalSpec(BaseModel):
    """Clinical question: 'N consecutive readings, each separated by D days'.

    Used for serial-monitoring rules (PSA, HbA1c, eGFR) where one
    reading above a threshold is not enough -- the clinician wants the
    abnormality to persist before the rule fires.
    """

    model_config = {"extra": "forbid"}

    count: int = Field(
        ge=2,
        le=10,
        description=(
            "Number of CONSECUTIVE readings (in time order) that must "
            "all satisfy the leaf's operator/value condition. Must be "
            "at least 2 -- 1 collapses to ABSOLUTE mode."
        ),
    )
    interval_min_days: int = Field(
        ge=_MIN_INTERVAL_DAYS,
        le=_MAX_WINDOW_DAYS,
        description="Minimum spacing between adjacent readings in days.",
    )
    interval_max_days: int | None = Field(
        default=None,
        ge=_MIN_INTERVAL_DAYS,
        le=_MAX_WINDOW_DAYS,
        description=(
            "Maximum spacing between adjacent readings in days. "
            "Optional; when omitted, only the minimum spacing is "
            "enforced."
        ),
    )

    @model_validator(mode="after")
    def _check_interval_order(self) -> "TemporalSpec":
        if (
            self.interval_max_days is not None
            and self.interval_max_days < self.interval_min_days
        ):
            raise ObservationLeafValidationError(
                "TemporalSpec.interval_max_days must be greater than or "
                "equal to interval_min_days."
            )
        return self


class ReferenceRangeSpec(BaseModel):
    """Clinical question: 'compare to the patient's normal range'.

    Reference ranges are typically sex- and age-banded (for example
    creatinine has a different upper limit for men, women, and
    children). The evaluator looks up the band for the patient at
    evaluation time; the leaf only declares which bound and which
    multiple to compare against.
    """

    model_config = {"extra": "forbid"}

    bound: ReferenceRangeBound = Field(
        description=(
            "Which reference-range bound to compare against. 'upper' "
            "for ULN (alanine transaminase, creatinine, blood "
            "pressure); 'lower' for LLN (haemoglobin, eGFR)."
        )
    )
    multiple_of_range: float = Field(
        default=1.0,
        gt=0.0,
        le=20.0,
        description=(
            "Multiplier applied to the bound before the comparison. "
            "1.0 means 'above ULN'; 3.0 means 'above 3 x ULN', the "
            "common shorthand for severe transaminase elevation."
        ),
    )


class TrendSpec(BaseModel):
    """Clinical question: 'value changed by D over W days'.

    Delta is computed as latest - oldest within the window, where
    'latest' is the most recent reading and 'oldest' is the earliest
    reading still inside the window. Percent mode normalises against
    the oldest reading so '25 percent fall in eGFR over 12 months'
    works regardless of baseline.
    """

    model_config = {"extra": "forbid"}

    delta_kind: DeltaKind = Field(
        description=(
            "absolute = (latest - oldest), in the leaf's unit; "
            "percent = 100 * (latest - oldest) / max(abs(oldest), 1e-9)."
        )
    )
    window_days: int = Field(
        ge=_MIN_WINDOW_DAYS,
        le=_MAX_WINDOW_DAYS,
        description=(
            "Window in days over which the delta is measured. Must be "
            "at least one day."
        ),
    )


class AggregateSpec(BaseModel):
    """Clinical question: 'the average / median / max of the last N readings'.

    Used to smooth out single noisy readings before a rule fires. For
    example QOF DM_018 looks at the 'most recent HbA1c'; a smoother
    variant of the same question is 'mean of the last 3 HbA1cs'.
    """

    model_config = {"extra": "forbid"}

    kind: AggregationFunction = Field(
        description=(
            "Reduction applied to the lookback window before "
            "comparison. mean / median / min / max."
        )
    )
    lookback_n: int = Field(
        ge=_MIN_LOOKBACK_N,
        le=_MAX_LOOKBACK_N,
        description=(
            "Number of most-recent readings to include in the "
            "aggregation. Fails closed when fewer than this number "
            "of readings sit inside within_days."
        ),
    )


class ObservationLeaf(BaseModel):
    """One numeric-observation question inside a logic tree.

    The leaf is intentionally flat at the top level and uses nested
    sub-models for each evaluation mode so:
      - The wire JSON stays human-readable.
      - The Pydantic validator can enforce 'exactly one mode at a time'
        in a single model_validator.
      - The compiler / evaluator can pattern-match on the populated
        sub-model rather than parsing free-form flags.

    Field discipline:
      - ``observable_id`` is the canonical SNOMED concept id for the
        observable procedure / panel (for example 365632008 for
        platelet count). It is what binds the leaf to the patient
        bundle's observation rows.
      - ``unit`` is the wire unit the rule was authored in. The
        evaluator canonicalises it before comparison.
      - ``within_days`` defaults to 365 -- matches NICE's most common
        recency wording. Set higher for chronic-disease screening
        rules, lower for acute thresholds.
    """

    model_config = {"extra": "forbid"}

    kind: Literal["OBSERVATION"] = Field(
        default="OBSERVATION",
        description=(
            "Discriminator. Always OBSERVATION; included so the leaf "
            "round-trips through the same LogicNode union as CONCEPT "
            "and DEMOGRAPHIC."
        ),
    )

    node_id: str | None = Field(
        default=None,
        description=(
            "Stable client-side id for tree mutations (replace, "
            "remove). Optional on the wire so server-generated trees "
            "can defer assigning ids until persistence."
        ),
    )

    observable_id: str = Field(
        min_length=1,
        description=(
            "SNOMED concept id of the observable the leaf asks about "
            "(for example 365632008 = 'Platelet count - observation'). "
            "Bind to the patient bundle's observation rows."
        ),
    )
    observable_term: str = Field(
        default="",
        description=(
            "Plain-English label of the observable, surfaced in the "
            "sentence canvas so reviewers do not need to look up the "
            "SNOMED preferred term. Optional but recommended."
        ),
    )

    operator: ComparisonOperator = Field(
        description=(
            "Comparison operator. >=, <=, >, <, =, or between. "
            "between requires a [low, high] value tuple; every other "
            "operator requires a scalar value."
        )
    )
    value: float | tuple[float, float] | list[float] = Field(
        description=(
            "Threshold the patient's reading is compared against. "
            "Scalar for >=, <=, >, <, =. List or tuple [low, high] "
            "for the 'between' operator (inclusive on both ends)."
        )
    )
    unit: str = Field(
        default="",
        description=(
            "Unit string the rule was authored in (for example "
            "'10*9/L', 'mmol/L', 'mmHg'). Optional when the threshold "
            "is already in the observable's canonical unit. The "
            "evaluator canonicalises via libs.units.observable_units "
            "before comparison."
        ),
    )
    within_days: int = Field(
        default=365,
        ge=_MIN_WINDOW_DAYS,
        le=_MAX_WINDOW_DAYS,
        description=(
            "Recency window in days. Readings older than this are "
            "ignored. Default 365 (one year) matches the most common "
            "NICE wording. Capped at 7300 days (20 years)."
        ),
    )

    temporal: TemporalSpec | None = Field(
        default=None,
        description=(
            "Set this for 'N consecutive readings, D days apart' "
            "patterns. Mutually exclusive with reference_range, "
            "trend, and aggregation."
        ),
    )
    reference_range: ReferenceRangeSpec | None = Field(
        default=None,
        description=(
            "Set this when the threshold is relative to the patient's "
            "reference range (ULN / LLN), not an absolute value. "
            "Mutually exclusive with temporal, trend, and aggregation."
        ),
    )
    trend: TrendSpec | None = Field(
        default=None,
        description=(
            "Set this for 'value changed by D over W days' rules. "
            "Mutually exclusive with temporal, reference_range, and "
            "aggregation."
        ),
    )
    aggregation: AggregateSpec | None = Field(
        default=None,
        description=(
            "Set this when the comparison is against an aggregate of "
            "the last N readings (mean / median / min / max). "
            "Mutually exclusive with temporal, reference_range, and "
            "trend."
        ),
    )

    @model_validator(mode="after")
    def _check_value_matches_operator(self) -> "ObservationLeaf":
        op = self.operator
        val = self.value
        if op == "between":
            seq = _coerce_value_pair(val)
            if seq is None:
                raise ObservationLeafValidationError(
                    "OBSERVATION operator 'between' requires value to "
                    "be a [low, high] pair."
                )
            low, high = seq
            if low > high:
                raise ObservationLeafValidationError(
                    "OBSERVATION 'between' value must satisfy low <= "
                    "high; got [%r, %r]." % (low, high)
                )
            self.value = (low, high)
            return self
        if not isinstance(val, (int, float)):
            raise ObservationLeafValidationError(
                f"OBSERVATION operator {op!r} requires a scalar "
                f"value; got {type(val).__name__}."
            )
        self.value = float(val)
        return self

    @model_validator(mode="after")
    def _check_one_mode(self) -> "ObservationLeaf":
        modes = [
            ("temporal", self.temporal),
            ("reference_range", self.reference_range),
            ("trend", self.trend),
            ("aggregation", self.aggregation),
        ]
        active = [name for name, spec in modes if spec is not None]
        if len(active) > 1:
            raise ObservationLeafValidationError(
                "OBSERVATION leaf may set at most one of temporal, "
                "reference_range, trend, aggregation; got: "
                + ", ".join(active)
            )
        return self

    @model_validator(mode="after")
    def _check_window_envelope(self) -> "ObservationLeaf":
        # The trend window must fit inside within_days, otherwise the
        # evaluator would have to pull readings older than the leaf
        # claims to care about.
        if self.trend is not None and self.trend.window_days > self.within_days:
            raise ObservationLeafValidationError(
                "OBSERVATION trend.window_days "
                f"({self.trend.window_days}) cannot exceed within_days "
                f"({self.within_days})."
            )
        # Same envelope for the temporal interval bounds: the latest
        # reading minus interval_min_days * (count - 1) must still fit
        # inside the recency window.
        if self.temporal is not None:
            min_span = self.temporal.interval_min_days * (
                self.temporal.count - 1
            )
            if min_span > self.within_days:
                raise ObservationLeafValidationError(
                    "OBSERVATION temporal pattern needs at least "
                    f"{min_span} days of history, which exceeds "
                    f"within_days ({self.within_days})."
                )
        return self

    def mode(self) -> str:
        """Return a short string identifying which evaluation mode is active.

        One of ``absolute``, ``temporal``, ``reference_range``,
        ``trend``, ``aggregate``. Used by the evaluator to dispatch and
        by the sentence renderer to pick the right phrase.
        """
        if self.temporal is not None:
            return "temporal"
        if self.reference_range is not None:
            return "reference_range"
        if self.trend is not None:
            return "trend"
        if self.aggregation is not None:
            return "aggregate"
        return "absolute"


def _coerce_value_pair(val: Any) -> tuple[float, float] | None:
    """Coerce a between-operator value into a (low, high) tuple of floats.

    Accepts a 2-element list or tuple of numbers. Returns None when the
    shape is invalid so the caller can raise a precise error.
    """
    if isinstance(val, (list, tuple)) and len(val) == 2:
        try:
            return float(val[0]), float(val[1])
        except (TypeError, ValueError):
            return None
    return None
