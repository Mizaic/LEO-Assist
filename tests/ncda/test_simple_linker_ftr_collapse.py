"""Tests for the near-duplicate FTR collapse step in ``simple_linker``.

Background:
    PRISM 2WW questionnaire encounters can be entered twice on the same day
    (e.g. clinician starts the form at 16:35 and the secretary finalises it
    at 16:55, generating two ``Encounter`` nodes).  Without collapsing them
    the simple linker builds two parallel pathways and the detector persists
    duplicate ``EpisodeOfCare`` nodes.  This module covers the collapse
    logic that prevents that.
"""

from __future__ import annotations

from services.analysis_worker.app.ncda_detector.simple_linker import (
    EncounterRow,
    NEAR_FTR_COLLAPSE_DAYS,
    _collapse_near_duplicate_ftrs,
    link_patient,
)


def _ftr(
    encounter_id: str,
    encounter_date: str,
    *,
    site: str | None = None,
    text: str = "PRISM 2WW questionnaire started",
) -> EncounterRow:
    return EncounterRow(
        encounter_id=encounter_id,
        encounter_date=encounter_date,
        role="ftr",
        outcome=None,
        text=text,
        site=site,  # type: ignore[arg-type]
    )


def _dx(
    encounter_id: str,
    encounter_date: str,
    *,
    site: str | None = None,
    outcome: str = "cancer_found",
    text: str = "Major: Carcinoma of caecum (X78gM) (New Episode)",
) -> EncounterRow:
    return EncounterRow(
        encounter_id=encounter_id,
        encounter_date=encounter_date,
        role="dx",
        outcome=outcome,  # type: ignore[arg-type]
        text=text,
        site=site,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# _collapse_near_duplicate_ftrs unit tests
# ---------------------------------------------------------------------------

def test_same_day_compatible_sites_collapse_to_one():
    a = _ftr("A", "2025-06-27", site=None, text="PRISM 2WW Hepatobiliary - questionnaire started")
    b = _ftr(
        "B",
        "2025-06-27",
        site="upper_gi",
        text="PRISM 2WW Hepatobiliary - questionnaire started (finalised). "
        "Fast track referral for suspected upper GI cancer (XaMeJ)",
    )
    kept, dropped = _collapse_near_duplicate_ftrs([a, b], window_days=1)
    assert len(kept) == 1
    assert kept[0].encounter_id == "B"
    assert len(dropped) == 1
    assert dropped[0][0].encounter_id == "A"
    assert dropped[0][1].encounter_id == "B"


def test_same_day_same_site_keeps_more_canonical():
    a = _ftr("A", "2025-06-27", site="upper_gi", text="PRISM 2WW questionnaire started")
    b = _ftr(
        "B",
        "2025-06-27",
        site="upper_gi",
        text="Fast track referral for suspected upper GI cancer (XaMeJ)",
    )
    kept, _ = _collapse_near_duplicate_ftrs([a, b], window_days=1)
    assert len(kept) == 1
    # B has the explicit XaMeJ Read code, so it should be kept.
    assert kept[0].encounter_id == "B"


def test_different_sites_NOT_collapsed_even_same_day():
    a = _ftr("A", "2025-06-27", site="breast")
    b = _ftr("B", "2025-06-27", site="urological")
    kept, dropped = _collapse_near_duplicate_ftrs([a, b], window_days=1)
    assert len(kept) == 2
    assert dropped == []


def test_haematological_NOT_collapsed_with_breast():
    """`_sites_compatible` (used for Dx linking) treats haematological as a
    wildcard, but the FTR collapse must NOT — those are clinically distinct
    pathways even when same-day.
    """
    a = _ftr("A", "2025-06-27", site="breast")
    b = _ftr("B", "2025-06-27", site="haematological")
    kept, _ = _collapse_near_duplicate_ftrs([a, b], window_days=1)
    assert len(kept) == 2


def test_outside_window_NOT_collapsed():
    a = _ftr("A", "2025-06-27", site="upper_gi")
    b = _ftr("B", "2025-07-05", site="upper_gi")
    kept, _ = _collapse_near_duplicate_ftrs([a, b], window_days=1)
    assert len(kept) == 2


def test_within_extended_window_collapsed():
    a = _ftr("A", "2025-06-27", site="upper_gi")
    b = _ftr("B", "2025-06-30", site="upper_gi")
    kept, _ = _collapse_near_duplicate_ftrs([a, b], window_days=7)
    assert len(kept) == 1


def test_three_same_day_collapsed_to_one():
    a = _ftr("A", "2025-06-27", site=None)
    b = _ftr("B", "2025-06-27", site="upper_gi")
    c = _ftr(
        "C",
        "2025-06-27",
        site="upper_gi",
        text="Fast track referral for suspected upper GI cancer (XaMeJ)",
    )
    kept, _ = _collapse_near_duplicate_ftrs([a, b, c], window_days=1)
    assert len(kept) == 1
    assert kept[0].encounter_id == "C"


def test_empty_input_returns_empty():
    assert _collapse_near_duplicate_ftrs([], window_days=1) == ([], [])


# ---------------------------------------------------------------------------
# link_patient end-to-end with duplicate FTRs (the 4940120139 regression)
# ---------------------------------------------------------------------------

def test_link_patient_collapses_4940120139_style_duplicates():
    """Replays the 4940120139 caecal-cancer scenario.

    Two same-day FTR encounters (PRISM start + finalise) plus a single Dx.
    Without collapse the linker would build TWO Cohort 1a pathways and two
    duplicate episodes.  With collapse there should be exactly one pathway.
    Uses upper_gi end-to-end so a clean linkage forms.
    """
    ftr_started = _ftr(
        "A_started",
        "2025-06-27",
        site=None,
        text="PRISM 2WW Hepatobiliary - questionnaire started. Clinical Supervision",
    )
    ftr_finalised = _ftr(
        "B_finalised",
        "2025-06-27",
        site="upper_gi",
        text="PRISM 2WW Hepatobiliary - questionnaire started (finalised). "
        "Fast track referral for suspected upper GI cancer (XaMeJ)",
    )
    dx = _dx(
        "DX",
        "2025-07-22",
        site="upper_gi",
        text="Major: Adenocarcinoma of stomach (X78a1) (New Episode)",
    )
    pathways = link_patient(
        "4940120139", [ftr_started, ftr_finalised, dx]
    )
    cohort_1a = [p for p in pathways if p.cohort == "1a"]
    assert len(cohort_1a) == 1, f"Expected 1 cohort-1a pathway, got {len(cohort_1a)}"
    assert cohort_1a[0].ftr is not None
    assert cohort_1a[0].ftr.encounter_id == "B_finalised"
    assert cohort_1a[0].dx.encounter_id == "DX"  # type: ignore[union-attr]


def test_link_patient_collapses_with_unknown_site_dx():
    """When the Dx has no inferred site (e.g. 'Metastatic carcinoma' alone)
    the upper_gi FTR should still link AND the same-day duplicate FTR should
    not produce a second pathway.
    """
    ftr_started = _ftr(
        "A_started",
        "2025-06-27",
        site=None,
        text="PRISM 2WW questionnaire started",
    )
    ftr_finalised = _ftr(
        "B_finalised",
        "2025-06-27",
        site="upper_gi",
        text="Fast track referral for suspected upper GI cancer (XaMeJ)",
    )
    dx = _dx(
        "DX",
        "2025-07-22",
        site=None,
        text="Major: Metastatic carcinoma (XM1GJ) (New Episode)",
    )
    pathways = link_patient(
        "P", [ftr_started, ftr_finalised, dx]
    )
    cohort_1a = [p for p in pathways if p.cohort == "1a"]
    assert len(cohort_1a) == 1
    assert cohort_1a[0].ftr is not None
    assert cohort_1a[0].ftr.encounter_id == "B_finalised"


def test_link_patient_two_distinct_sites_kept_separate():
    """Two same-day FTRs for different sites must produce two pathways."""
    ftr_breast = _ftr(
        "F_breast",
        "2025-06-27",
        site="breast",
        text="Fast track referral for suspected breast cancer (XaMeC)",
    )
    ftr_lower = _ftr(
        "F_lower",
        "2025-06-27",
        site="lower_gi",
        text="Fast track referral for suspected lower GI cancer (Xaalp)",
    )
    dx_breast = _dx(
        "DX_b",
        "2025-08-01",
        site="breast",
        text="Major: Carcinoma of breast (X78WM) (New Episode)",
    )
    dx_lower = _dx(
        "DX_l",
        "2025-08-15",
        site="lower_gi",
        text="Major: Carcinoma of caecum (X78gM) (New Episode)",
    )
    pathways = link_patient(
        "P", [ftr_breast, ftr_lower, dx_breast, dx_lower]
    )
    cohort_1a = sorted(
        [p for p in pathways if p.cohort == "1a"], key=lambda p: p.ftr_site or ""
    )
    assert len(cohort_1a) == 2
    sites = {p.ftr_site for p in cohort_1a}
    assert sites == {"breast", "lower_gi"}


def test_default_collapse_window_is_one_day():
    assert NEAR_FTR_COLLAPSE_DAYS == 1
