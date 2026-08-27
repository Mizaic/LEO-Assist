"""Standard NHS blood panel presets for the referral form teacher.

Atlas trace:
  DI: DI-5C9CA57B  (form checkbox normalisation)
  DI: DI-26546721  (referral form teaching)

The blood results table on an NHS urgent suspected cancer referral is
the same across trusts. Without a preset, whoever teaches the form has
to hand-type every battery, every analyte, and every SNOMED code. This
module holds that table once so the form teacher can load it in one
click and then delete any row the local form does not use.

Every SNOMED code here was checked against the loaded UK SNOMED CT
release in the terminology graph. Batteries use the ``procedure``
semantic tag; analytes use ``observable entity``. Where no safe concept
exists the code is left empty and listed in ``unverified_preset_codes``
for clinical review -- never invented.

Grouping note: the printed form lays the table out in two columns, so
ESR sits beside CRP and INR sits beside the thyroid tests. Those are
separate tests clinically, so they are separate batteries here. That
stops a mention of "TFTs" seeding an INR observable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PresetAnalyte:
    """One result row inside a blood test battery."""

    label: str
    snomed_code: str
    display: str


@dataclass(frozen=True)
class PresetBattery:
    """One blood test battery and the result rows it reports."""

    label: str
    procedure_snomed: str
    procedure_display: str
    analytes: tuple[PresetAnalyte, ...]
    aliases: tuple[str, ...] = ()


def _a(label: str, code: str, display: str) -> PresetAnalyte:
    return PresetAnalyte(label=label, snomed_code=code, display=display)


# LONG DECLARATION: canonical clinical data table, not branching logic.
NHS_BLOOD_PANEL_BATTERIES: tuple[PresetBattery, ...] = (
    PresetBattery(
        label="FBC",
        procedure_snomed="26604007",
        procedure_display="Complete blood count",
        aliases=("full blood count",),
        analytes=(
            _a("Hb", "1022431000000105", "Haemoglobin estimation"),
            _a("WCC", "1110441000000100", "White blood cell count in blood"),
            _a("Plts", "1022651000000100", "Platelet count"),
            _a("MCV", "1022491000000106", "Mean corpuscular volume"),
            _a("Neut", "1022551000000104", "Neutrophil count"),
        ),
    ),
    PresetBattery(
        label="UE",
        procedure_snomed="252167001",
        procedure_display="Measurement of urea and electrolytes",
        aliases=("u&e", "u&es", "ues", "urea and electrolytes"),
        analytes=(
            _a("Na", "1000661000000107", "Serum sodium level"),
            _a("K", "1000651000000109", "Serum potassium level"),
            _a("Urea", "1000951000000103", "Serum urea level"),
            _a("Creat", "1000731000000107", "Serum creatinine level"),
            _a("eGFR", "1011481000000105", "Estimated glomerular filtration rate"),
        ),
    ),
    PresetBattery(
        label="LFT",
        procedure_snomed="26958001",
        procedure_display="Hepatic function panel",
        aliases=("lfts", "liver function test", "liver function tests"),
        analytes=(
            _a("ALT", "1018251000000107", "Serum alanine aminotransferase level"),
            _a("Alk Phos", "1000621000000104", "Serum alkaline phosphatase level"),
            _a("Bili", "997591000000109", "Serum total bilirubin level"),
            _a("Alb", "1000821000000103", "Serum albumin level"),
            _a("GGT", "1000861000000106", "Serum gamma-glutamyl transferase level"),
        ),
    ),
    PresetBattery(
        label="CRP",
        procedure_snomed="135842001",
        procedure_display="Serum C reactive protein level",
        aliases=("c reactive protein",),
        analytes=(_a("CRP", "1001371000000100", "Serum C reactive protein level"),),
    ),
    PresetBattery(
        label="ESR",
        procedure_snomed="416838001",
        procedure_display="Erythrocyte sedimentation rate measurement",
        aliases=("erythrocyte sedimentation rate",),
        analytes=(_a("ESR", "1022511000000103", "Erythrocyte sedimentation rate"),),
    ),
    PresetBattery(
        label="TFTs",
        procedure_snomed="35650009",
        procedure_display="Thyroid panel",
        aliases=("tft", "thyroid function test", "thyroid function tests"),
        analytes=(
            _a("TSH", "1022791000000101", "Serum thyroid stimulating hormone level"),
            _a("Free T4", "1030801000000101", "Free thyroxine level"),
        ),
    ),
    PresetBattery(
        label="INR",
        procedure_snomed="440685005",
        procedure_display="Calculation of international normalized ratio",
        aliases=("international normalised ratio",),
        analytes=(_a("INR", "165581004", "International normalized ratio"),),
    ),
    PresetBattery(
        label="Bone",
        procedure_snomed="167036008",
        procedure_display="Bone profile",
        aliases=("bone profile",),
        analytes=(
            _a("Ca", "1000691000000101", "Serum calcium level"),
            _a("Ca cor", "", "Corrected serum calcium level"),
            _a("Ca adj", "935051000000108", "Serum adjusted calcium concentration"),
            _a("Phos", "1000701000000101", "Serum inorganic phosphate level"),
        ),
    ),
    PresetBattery(
        label="Iron",
        procedure_snomed="",
        procedure_display="Iron studies",
        aliases=("iron studies", "iron profile"),
        analytes=(
            _a("Ferritin", "993381000000106", "Serum ferritin level"),
            _a("Iron Saturation", "991831000000103", "Transferrin saturation index"),
            _a("TIBC", "1015451000000101", "Serum total iron binding capacity"),
        ),
    ),
    PresetBattery(
        label="Vitamins",
        procedure_snomed="395144002",
        procedure_display="B12/folate level",
        aliases=("vitamin", "b12 and folate", "haematinics"),
        analytes=(
            _a("B12", "993391000000108", "Serum vitamin B12 level"),
            _a("Folate", "993411000000108", "Serum folate level"),
        ),
    ),
    PresetBattery(
        label="Lipids",
        procedure_snomed="16254007",
        procedure_display="Lipid panel",
        aliases=("lipid profile", "lipid panel"),
        analytes=(
            _a("Chol", "1005671000000105", "Serum cholesterol level"),
            _a(
                "LDL",
                "1022191000000100",
                "Serum low density lipoprotein cholesterol level",
            ),
            _a(
                "HDL",
                "1005681000000107",
                "Serum high density lipoprotein cholesterol level",
            ),
            _a(
                "Chol:HDL ratio",
                "1015681000000109",
                "Serum cholesterol/high density lipoprotein ratio",
            ),
            _a("Tri", "1005691000000109", "Serum triglycerides level"),
        ),
    ),
    PresetBattery(
        label="Random Glucose",
        procedure_snomed="271061004",
        procedure_display="Random blood glucose measurement",
        aliases=("random glucose",),
        analytes=(
            _a("Random glucose", "1089381000000101", "Random blood glucose level"),
        ),
    ),
    PresetBattery(
        label="Fasting Glucose",
        procedure_snomed="271062006",
        procedure_display="Fasting blood glucose measurement",
        aliases=("fasting glucose",),
        analytes=(
            _a("Fasting glucose", "997681000000108", "Fasting blood glucose level"),
        ),
    ),
    PresetBattery(
        label="Fasting Chol.",
        procedure_snomed="315017003",
        procedure_display="Fasting cholesterol level",
        aliases=("fasting chol", "fasting cholesterol"),
        analytes=(
            _a(
                "Fasting Chol.",
                "1083761000000106",
                "Serum fasting total cholesterol level",
            ),
        ),
    ),
    PresetBattery(
        label="HbA1c",
        procedure_snomed="43396009",
        procedure_display="Hemoglobin A1c measurement",
        aliases=("haemoglobin a1c", "hba1c"),
        analytes=(_a("HbA1c", "1003671000000109", "Haemoglobin A1c level"),),
    ),
    PresetBattery(
        label="CA 125",
        procedure_snomed="909121000000107",
        procedure_display="Measurement of cancer antigen 125 in serum specimen",
        aliases=("ca125", "cancer antigen 125"),
        analytes=(_a("CA 125", "1000461000000109", "Serum cancer antigen 125 level"),),
    ),
)

# Rows where no safe SNOMED concept was found in the loaded UK release.
# The form teacher can still use the row; the code stays empty until a
# clinician confirms a concept. Never fill these in by guessing.
_UNVERIFIED: dict[str, str] = {
    "Iron": (
        "No 'Iron studies' panel concept exists in the loaded UK release. "
        "Serum iron measurement (42950004) is a single analyte, not the "
        "panel, so it would be wrong here. Needs clinical review."
    ),
    "Bone / Ca cor": (
        "Only 'Serum adjusted calcium concentration' (935051000000108) "
        "exists. Corrected and adjusted calcium are usually the same "
        "result reported twice, so reusing the code would create a "
        "duplicate observable. Needs clinical review."
    ),
}


def _normalise(label: str) -> str:
    return "".join(ch for ch in label.lower() if ch.isalnum())


def _match_keys(battery: PresetBattery) -> set[str]:
    keys = {_normalise(battery.label), _normalise(battery.procedure_display)}
    keys.update(_normalise(alias) for alias in battery.aliases)
    return {key for key in keys if key}


def battery_for_label(label: str) -> PresetBattery | None:
    """Return the preset battery matching ``label``, or None.

    Matching ignores case, spaces, and punctuation, so "U&E", "ues",
    and "UE" all resolve to the same battery.
    """
    key = _normalise(label)
    if not key:
        return None
    for battery in NHS_BLOOD_PANEL_BATTERIES:
        if key in _match_keys(battery):
            return battery
    return None


def preset_analytes_for_label(label: str) -> list[dict[str, str]]:
    """Return the preset analyte rows for a battery label.

    Returns an empty list when the label is not a known battery, so
    callers can use this as a safe fallback for a taught battery that
    has no analytes of its own.
    """
    battery = battery_for_label(label)
    if battery is None:
        return []
    return [
        {"label": a.label, "snomed_code": a.snomed_code, "display": a.display}
        for a in battery.analytes
    ]


def blood_panel_preset_payload() -> list[dict[str, Any]]:
    """Return the preset as ordered_tests form schema items.

    The shape matches ``FormSchemaItemRequest`` so the UI can drop the
    rows straight into a taught ordered_tests section.
    """
    return [
        {
            "pattern": battery.label,
            "entity_text": battery.procedure_display,
            "semantic_tag": "procedure",
            "assertion": "present",
            "procedure_snomed": battery.procedure_snomed,
            "procedure_display": battery.procedure_display,
            "analytes": preset_analytes_for_label(battery.label),
            "value_placeholder": "",
        }
        for battery in NHS_BLOOD_PANEL_BATTERIES
    ]


def unverified_preset_codes() -> dict[str, str]:
    """Return rows that still need a clinician to confirm a SNOMED code."""
    return dict(_UNVERIFIED)
