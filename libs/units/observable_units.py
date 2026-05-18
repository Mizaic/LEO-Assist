"""Canonical-unit registry and reference ranges for clinical observables.

Atlas trace (Phase 5b):
    UN: UN-26E57FA1
    DI: DI-7790EEA5
    DO: DO-710270EF
    Risk: R-555C8691
    VT: VT-404C1E2C

Two responsibilities, kept in one module so they cannot drift:

  1. Per-observable canonical unit and unit-conversion factors. The
     evaluator uses these to compare a patient's reading (in whatever
     unit was recorded in their notes) against a rule's threshold (in
     whatever unit the rule was authored in). Both sides are converted
     to the canonical unit before comparison.

  2. Per-observable reference ranges, optionally banded by sex and
     age. Used by the OBSERVATION leaf's reference_range mode (for
     example "above 3 x ULN of ALT").

Curation rules:
  - Observable id is a SNOMED concept id of a numeric observable
    (semantic tag = "observable entity" or "procedure").
  - Canonical unit follows the UCUM string convention used by HL7 FHIR
    (for example '10*9/L' for platelets, 'mmol/L' for HbA1c IFCC,
    'mg/L' for serum ferritin). Display strings ('x10^9/L', 'mmHg')
    are mapped to UCUM via the alias table.
  - Reference ranges are seeded from NICE clinical knowledge summaries
    and the BNF; every entry is marked with a source string so an
    auditor can see provenance. Entries are 'awaiting clinical review'
    until a clinical reviewer signs off.
  - Conversions are linear (factor + offset). Non-linear conversions
    (for example pH) are rejected at registration time -- the editor
    must use the canonical unit directly.

Adding a new observable:
  - Append a new ``ObservableSpec`` to ``OBSERVABLE_UNIT_REGISTRY``
    with the canonical unit, every reasonable input alias, and the
    reference ranges if known.
  - Re-run ``tests/test_observable_units.py`` to confirm the new
    entry round-trips cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal


class UnknownObservableError(KeyError):
    """Raised when an observable_id has no canonical unit registered.

    Subclassed from KeyError so the compiler can keep using the
    standard 'unknown observable' wording reviewers see for unknown
    SNOMED concepts.
    """


class UnitConversionError(ValueError):
    """Raised when a value cannot be converted to the canonical unit.

    Causes include: the input unit is not registered for this
    observable, the input unit has a non-linear relationship to the
    canonical unit (rare; pH, dB), or the value is non-finite.
    """


@dataclass(frozen=True)
class UnitConversion:
    """Linear conversion from an input unit to the canonical unit.

    canonical_value = input_value * factor + offset

    Most clinical units are pure scalar ratios (factor only); the
    offset slot is reserved for the temperature case ('degF' to 'Cel').
    """

    factor: float
    offset: float = 0.0


@dataclass(frozen=True)
class ReferenceRange:
    """Numeric reference range for an observable, banded by patient demographic.

    Bounds are in the canonical unit. ``sex`` and ``age_min_years`` /
    ``age_max_years`` describe the band the range applies to; the
    evaluator picks the tightest matching band at evaluation time.
    A band that omits sex applies to both sexes; bands that omit
    age bounds apply to all ages.
    """

    lower: float | None
    upper: float | None
    unit: str
    source: str
    sex: Literal["female", "male"] | None = None
    age_min_years: float | None = None
    age_max_years: float | None = None
    notes: str = ""


@dataclass(frozen=True)
class ObservableSpec:
    """One observable's canonical unit, aliases, and reference ranges.

    Aliases is a mapping from any string the rule editor or ingest
    pipeline might encounter to the conversion that turns it into the
    canonical unit. The canonical unit itself is implicitly registered
    as the identity conversion so callers do not need to spell it
    twice.
    """

    observable_id: str
    canonical_unit: str
    display_name: str
    semantic_tag: str
    aliases: dict[str, UnitConversion] = field(default_factory=dict)
    reference_ranges: tuple[ReferenceRange, ...] = ()
    notes: str = ""


# ---------------------------------------------------------------------------
# Helpers used by the registry below to keep entries terse.
# ---------------------------------------------------------------------------


def _identity() -> UnitConversion:
    """Conversion that leaves the value unchanged."""
    return UnitConversion(factor=1.0, offset=0.0)


def _scale(factor: float) -> UnitConversion:
    """Scalar-only conversion: canonical = input * factor."""
    return UnitConversion(factor=factor, offset=0.0)


# ---------------------------------------------------------------------------
# OBSERVABLE_UNIT_REGISTRY
#
# Seeded with the NICE NG12 (suspected cancer) / QOF observables we have
# encountered in the rule corpus to date, plus the high-volume primary-
# care observables (BP, HbA1c, eGFR, ferritin, ALT, weight, BMI). Every
# entry is marked 'awaiting clinical review' in the source field until a
# clinical reviewer signs it off in the design control system.
#
# When you add a new entry, follow the existing pattern:
#   - canonical_unit in UCUM
#   - aliases for every common display variant (case-sensitive)
#   - reference_ranges by sex/age band where known
# ---------------------------------------------------------------------------


_REGISTRY: dict[str, ObservableSpec] = {}


def _register(spec: ObservableSpec) -> None:
    """Add a spec to the registry, rejecting duplicates loudly."""
    if spec.observable_id in _REGISTRY:
        raise ValueError(
            f"Duplicate observable_id {spec.observable_id!r} in registry."
        )
    _REGISTRY[spec.observable_id] = spec


# Platelet count - observation. NICE NG12: 'thrombocytosis (platelet
# count of 400 x10^9/L or above)'.
_register(
    ObservableSpec(
        observable_id="365632008",
        canonical_unit="10*9/L",
        display_name="Platelet count",
        semantic_tag="observable entity",
        aliases={
            "10*9/L": _identity(),
            "10^9/L": _identity(),
            "x10^9/L": _identity(),
            "x10*9/L": _identity(),
            "/nL": _identity(),
            "K/uL": _identity(),
            "10*3/uL": _identity(),
            "10^3/uL": _identity(),
        },
        reference_ranges=(
            ReferenceRange(
                lower=150.0,
                upper=400.0,
                unit="10*9/L",
                source="NICE CKS / Pathology lab norms (awaiting clinical review)",
            ),
        ),
        notes="NICE NG12 threshold for suspected cancer pathway: >= 400.",
    )
)

# Haemoglobin. NICE NG12: 'iron-deficiency anaemia in men, or in women
# who are not menstruating'.
_register(
    ObservableSpec(
        observable_id="271026005",
        canonical_unit="g/L",
        display_name="Haemoglobin",
        semantic_tag="observable entity",
        aliases={
            "g/L": _identity(),
            "g/dL": _scale(10.0),
            "g/100mL": _scale(10.0),
        },
        reference_ranges=(
            ReferenceRange(
                lower=130.0,
                upper=170.0,
                unit="g/L",
                sex="male",
                age_min_years=18.0,
                source="WHO / NICE CKS (awaiting clinical review)",
            ),
            ReferenceRange(
                lower=120.0,
                upper=155.0,
                unit="g/L",
                sex="female",
                age_min_years=18.0,
                source="WHO / NICE CKS (awaiting clinical review)",
            ),
        ),
    )
)

# HbA1c (IFCC). QOF DM_018 / NICE NG28: '>= 58 mmol/mol' is the
# escalation threshold, '>= 64 mmol/mol' is the failed-control threshold.
_register(
    ObservableSpec(
        observable_id="1003671000000109",
        canonical_unit="mmol/mol",
        display_name="HbA1c (IFCC)",
        semantic_tag="observable entity",
        aliases={
            "mmol/mol": _identity(),
            # DCCT percent -> IFCC mmol/mol via NGSP master equation.
            "%": UnitConversion(factor=10.929, offset=-23.5),
            "% DCCT": UnitConversion(factor=10.929, offset=-23.5),
        },
        reference_ranges=(
            ReferenceRange(
                lower=20.0,
                upper=42.0,
                unit="mmol/mol",
                source="NICE NG28 normoglycaemia (awaiting clinical review)",
            ),
        ),
        notes="QOF DM_018 escalation threshold: >= 58 mmol/mol.",
    )
)

# Estimated glomerular filtration rate (eGFR). NICE NG203: CKD staging
# uses absolute eGFR plus a 25 percent fall over 12 months as a trend
# trigger -- the latter is what the OBSERVATION leaf's trend mode is
# designed for.
_register(
    ObservableSpec(
        observable_id="1011481000000105",
        canonical_unit="mL/min/{1.73_m2}",
        display_name="Estimated GFR",
        semantic_tag="observable entity",
        aliases={
            "mL/min/{1.73_m2}": _identity(),
            "mL/min/1.73m2": _identity(),
            "ml/min/1.73m2": _identity(),
            "mL/min/1.73 m2": _identity(),
        },
        reference_ranges=(
            ReferenceRange(
                lower=90.0,
                upper=None,
                unit="mL/min/{1.73_m2}",
                source="NICE NG203 stage G1 (awaiting clinical review)",
            ),
        ),
    )
)

# Serum creatinine. NICE NG203: AKI definition uses a 26 micromol/L
# rise over 48h. The trend mode supports this directly.
_register(
    ObservableSpec(
        observable_id="113075003",
        canonical_unit="umol/L",
        display_name="Serum creatinine",
        semantic_tag="observable entity",
        aliases={
            "umol/L": _identity(),
            "uMol/L": _identity(),
            "micromol/L": _identity(),
            "mg/dL": _scale(88.4),
        },
        reference_ranges=(
            ReferenceRange(
                lower=64.0,
                upper=104.0,
                unit="umol/L",
                sex="male",
                age_min_years=18.0,
                source="UK NEQAS (awaiting clinical review)",
            ),
            ReferenceRange(
                lower=49.0,
                upper=90.0,
                unit="umol/L",
                sex="female",
                age_min_years=18.0,
                source="UK NEQAS (awaiting clinical review)",
            ),
        ),
    )
)

# Alanine aminotransferase (ALT). Drug-induced liver injury rules
# typically read 'ALT > 3 x ULN' -- exactly the reference_range mode.
_register(
    ObservableSpec(
        observable_id="45896005",
        canonical_unit="U/L",
        display_name="Alanine aminotransferase",
        semantic_tag="observable entity",
        aliases={
            "U/L": _identity(),
            "IU/L": _identity(),
            "iu/L": _identity(),
        },
        reference_ranges=(
            ReferenceRange(
                lower=10.0,
                upper=40.0,
                unit="U/L",
                sex="male",
                age_min_years=18.0,
                source="UK NEQAS (awaiting clinical review)",
            ),
            ReferenceRange(
                lower=7.0,
                upper=35.0,
                unit="U/L",
                sex="female",
                age_min_years=18.0,
                source="UK NEQAS (awaiting clinical review)",
            ),
        ),
    )
)

# Serum ferritin. NICE NG12 IDA workup uses ferritin < 30 ng/mL.
_register(
    ObservableSpec(
        observable_id="269078001",
        canonical_unit="ug/L",
        display_name="Serum ferritin",
        semantic_tag="observable entity",
        aliases={
            "ug/L": _identity(),
            "ng/mL": _identity(),
            "mcg/L": _identity(),
        },
        reference_ranges=(
            ReferenceRange(
                lower=30.0,
                upper=400.0,
                unit="ug/L",
                sex="male",
                age_min_years=18.0,
                source="BSH 2021 (awaiting clinical review)",
            ),
            ReferenceRange(
                lower=15.0,
                upper=200.0,
                unit="ug/L",
                sex="female",
                age_min_years=18.0,
                source="BSH 2021 (awaiting clinical review)",
            ),
        ),
    )
)

# PSA - prostate specific antigen. NICE NG12 has age-banded thresholds
# (>= 3 for ages 50-69, >= 5 for >= 70) -- the absolute mode plus the
# DEMOGRAPHIC age leaf together cover this.
_register(
    ObservableSpec(
        observable_id="313730000",
        canonical_unit="ug/L",
        display_name="Prostate specific antigen",
        semantic_tag="observable entity",
        aliases={
            "ug/L": _identity(),
            "ng/mL": _identity(),
        },
        reference_ranges=(
            ReferenceRange(
                lower=0.0,
                upper=3.0,
                unit="ug/L",
                sex="male",
                age_min_years=50.0,
                age_max_years=69.999,
                source="NICE NG12 (awaiting clinical review)",
            ),
            ReferenceRange(
                lower=0.0,
                upper=5.0,
                unit="ug/L",
                sex="male",
                age_min_years=70.0,
                source="NICE NG12 (awaiting clinical review)",
            ),
        ),
    )
)

# Systolic blood pressure (clinic). NICE NG136 uses 140 / 90 as the
# clinic threshold, 135 / 85 for ABPM averages.
_register(
    ObservableSpec(
        observable_id="271649006",
        canonical_unit="mm[Hg]",
        display_name="Systolic blood pressure",
        semantic_tag="observable entity",
        aliases={
            "mm[Hg]": _identity(),
            "mmHg": _identity(),
            "mm Hg": _identity(),
        },
        reference_ranges=(
            ReferenceRange(
                lower=90.0,
                upper=140.0,
                unit="mm[Hg]",
                source="NICE NG136 clinic threshold (awaiting clinical review)",
            ),
        ),
    )
)

# Diastolic blood pressure (clinic).
_register(
    ObservableSpec(
        observable_id="271650006",
        canonical_unit="mm[Hg]",
        display_name="Diastolic blood pressure",
        semantic_tag="observable entity",
        aliases={
            "mm[Hg]": _identity(),
            "mmHg": _identity(),
            "mm Hg": _identity(),
        },
        reference_ranges=(
            ReferenceRange(
                lower=60.0,
                upper=90.0,
                unit="mm[Hg]",
                source="NICE NG136 clinic threshold (awaiting clinical review)",
            ),
        ),
    )
)

# Body weight. Used by aggregate (mean weight) and trend (weight loss
# over months) modes.
_register(
    ObservableSpec(
        observable_id="27113001",
        canonical_unit="kg",
        display_name="Body weight",
        semantic_tag="observable entity",
        aliases={
            "kg": _identity(),
            "g": _scale(0.001),
            "lb": _scale(0.45359237),
            "[lb_av]": _scale(0.45359237),
        },
        reference_ranges=(),
    )
)

# Body mass index. QOF AST_002 and OB_002 use absolute thresholds.
_register(
    ObservableSpec(
        observable_id="60621009",
        canonical_unit="kg/m2",
        display_name="Body mass index",
        semantic_tag="observable entity",
        aliases={
            "kg/m2": _identity(),
            "kg/m^2": _identity(),
            "kg/(m^2)": _identity(),
        },
        reference_ranges=(
            ReferenceRange(
                lower=18.5,
                upper=25.0,
                unit="kg/m2",
                source="WHO (awaiting clinical review)",
            ),
        ),
    )
)


# Public read-only view of the registry. Cast to dict for type-checker
# friendliness; mutation is discouraged but not blocked (Python).
OBSERVABLE_UNIT_REGISTRY: dict[str, ObservableSpec] = _REGISTRY


# Flat list of every reference range, keyed by observable_id. Built once
# at import time so the evaluator does not have to re-walk the registry
# on every leaf evaluation.
REFERENCE_RANGES: dict[str, tuple[ReferenceRange, ...]] = {
    obs_id: spec.reference_ranges
    for obs_id, spec in OBSERVABLE_UNIT_REGISTRY.items()
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_known_observable(observable_id: str) -> bool:
    """Return True when the observable has a canonical unit registered."""
    return observable_id in OBSERVABLE_UNIT_REGISTRY


def list_known_observables() -> list[str]:
    """Return every observable_id with a canonical unit registered."""
    return sorted(OBSERVABLE_UNIT_REGISTRY.keys())


def get_canonical_unit(observable_id: str) -> str:
    """Return the canonical unit for an observable, raising on unknowns.

    Used by the compiler to decide whether a rule is even compilable
    (a leaf whose observable has no canonical unit cannot be
    canonicalised). The evaluator never calls this directly -- it
    calls ``canonicalise_value`` instead.
    """
    spec = OBSERVABLE_UNIT_REGISTRY.get(observable_id)
    if spec is None:
        raise UnknownObservableError(observable_id)
    return spec.canonical_unit


def canonicalise_value(
    observable_id: str,
    value: float,
    unit: str,
) -> float:
    """Convert a value from its input unit to the observable's canonical unit.

    Raises:
        UnknownObservableError: when the observable_id is not registered.
        UnitConversionError: when the input unit is not a registered
            alias (or the canonical unit) for the observable, or the
            input value is non-finite.

    Returns:
        The value expressed in the canonical unit. When the input unit
        is already canonical, the value is returned unchanged (after a
        finite-number guard).
    """
    spec = OBSERVABLE_UNIT_REGISTRY.get(observable_id)
    if spec is None:
        raise UnknownObservableError(observable_id)

    if not _is_finite(value):
        raise UnitConversionError(
            f"Observable {observable_id} value {value!r} is not a finite number."
        )

    normalised_unit = unit.strip()
    if normalised_unit == spec.canonical_unit:
        return float(value)

    conv = spec.aliases.get(normalised_unit)
    if conv is None:
        raise UnitConversionError(
            f"Observable {observable_id} ({spec.display_name}) has no "
            f"conversion from unit {unit!r} to canonical unit "
            f"{spec.canonical_unit!r}. Add an alias to the registry, "
            f"or author the rule in the canonical unit."
        )
    return float(value) * conv.factor + conv.offset


def get_reference_range(
    observable_id: str,
    *,
    sex: str | None,
    age_years: float | None,
) -> ReferenceRange | None:
    """Return the tightest reference range matching the patient demographic.

    Returns None when the observable has no reference ranges
    registered, or when no band matches the patient (the evaluator
    treats both as 'no range available' and fails closed in the
    reference_range mode).

    Tightness wins by counting how many demographic constraints the
    band specifies (sex + age band beats sex-only beats unbanded).
    Within the same tightness, the first registered band wins so
    curators can document the priority order in the registry source.
    """
    bands = REFERENCE_RANGES.get(observable_id) or ()
    if not bands:
        return None
    sex_norm = (sex or "").strip().lower() or None
    candidates: list[tuple[int, ReferenceRange]] = []
    for band in bands:
        if not _band_matches(band, sex=sex_norm, age_years=age_years):
            continue
        score = _band_specificity(band)
        candidates.append((score, band))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1]


def _band_matches(
    band: ReferenceRange,
    *,
    sex: str | None,
    age_years: float | None,
) -> bool:
    """Return True when the patient demographics fall inside the band."""
    if band.sex is not None:
        if sex is None or sex != band.sex:
            return False
    if band.age_min_years is not None:
        if age_years is None or age_years < band.age_min_years:
            return False
    if band.age_max_years is not None:
        if age_years is None or age_years > band.age_max_years:
            return False
    return True


def _band_specificity(band: ReferenceRange) -> int:
    """Score how many demographic constraints a band specifies.

    Used to break ties when more than one band matches the patient.
    Sex-banded ranges beat unbanded; sex + age beats sex alone.
    """
    score = 0
    if band.sex is not None:
        score += 2
    if band.age_min_years is not None:
        score += 1
    if band.age_max_years is not None:
        score += 1
    return score


def _is_finite(value: float) -> bool:
    """Return True when the value is a finite real number.

    Plain ``math.isfinite`` is enough but the import is kept local so
    the wider module reads as 'just clinical data'.
    """
    import math

    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def known_aliases(observable_id: str) -> Iterable[str]:
    """Yield every unit string the observable accepts on input.

    Includes the canonical unit so callers can present a single
    'these units are accepted' picker without having to merge two
    sets.
    """
    spec = OBSERVABLE_UNIT_REGISTRY.get(observable_id)
    if spec is None:
        return ()
    return tuple({spec.canonical_unit, *spec.aliases.keys()})
