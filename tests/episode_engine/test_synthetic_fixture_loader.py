"""Integration VT for the timeline loader against the SYN-EE-001 synthetic
fixture (VT-LEO-AI-500 supplement, fixture-driven).

Loads the synthetic SYN-EE-001 timeline (a deterministic JSON file under
``tests/episode_engine/fixtures/``) through ``load_timeline`` using a
``FakePatientGraphClient`` shim, and asserts:

  - all 16 fixture encounters land in the encounter_index
  - the canonical 'Failed encounter' admin task IS present in the index
    so downstream stages can reason about it (and explicitly reject it
    as a treatment_started)
  - the canonical mastectomy encounter IS present with the
    '(New Episode)' marker preserved
  - same-day grouping puts the seven 2025-03-26 encounters under one
    date header in the trunk view
  - prompt safety stripping does not remove clinical text

The test uses NO real patient data and NO live Neo4j connection.
"""

from __future__ import annotations

from services.analysis_worker.app.episode_engine.timeline_loader import (
    load_timeline,
)
from tests.episode_engine.fixtures.loader import (
    FakePatientGraphClient,
    load_fixture,
)


def test_syn_ee_001_fixture_round_trips_through_loader():
    """VT-500-TC-007: synthetic SYN-EE-001 fixture loads cleanly with all
    encounters indexed and same-day grouping intact."""

    client = FakePatientGraphClient.from_fixture("SYN-EE-001")
    trunk, index, count = load_timeline("SYN-EE-001", client=client)

    # Every fixture encounter must round-trip into the index
    fixture = load_fixture("SYN-EE-001")
    expected_ids = {e["id"] for e in fixture["encounters"]}
    assert count == len(expected_ids)
    assert set(index.keys()) == expected_ids

    # Failed encounter MUST stay in the index so milestone_extractor can
    # explicitly refuse to anchor a milestone on it.
    failed_enc = index["syn-ee-001-enc-010"]
    assert "Failed encounter" in failed_enc["text"]
    assert failed_enc["date"] == "2025-05-02"

    # Canonical mastectomy encounter retains the (New Episode) marker.
    mastectomy = index["syn-ee-001-enc-015"]
    assert mastectomy["date"] == "2025-07-28"
    assert "Mastectomy of right breast" in mastectomy["text"]
    assert "(New Episode)" in mastectomy["text"]

    # Trunk view groups all seven 2025-03-26 encounters under one header
    assert "== 2025-03-26 (7 records) ==" in trunk

    # Trunk view also has headers for the other key dates
    for date_header in (
        "== 2025-04-28 (",
        "== 2025-05-02 (1 record) ==",
        "== 2025-05-19 (",
        "== 2025-07-28 (1 record) ==",
    ):
        assert date_header in trunk, f"Missing header: {date_header!r}"

    # Loader's full_snippet must preserve the diagnosis evidence for the
    # 2025-05-19 results-clinic letter.
    results_letter = index["syn-ee-001-enc-012"]
    assert "invasive ductal carcinoma" in results_letter["full_snippet"]
    assert "letrozole" in results_letter["full_snippet"]


def test_syn_ee_001_fixture_no_real_identifiers():
    """VT-500-TC-008: synthetic fixture contains no identifiers that look
    like real NHS numbers (10 digits starting with 1-7)."""

    fixture = load_fixture("SYN-EE-001")

    # Patient NHS number must be in the 999... test range
    assert fixture["patient"]["nhs_number"].startswith("999"), (
        "Synthetic fixture must use the NHS 999... test number range."
    )

    # No encounter text may contain a 10-digit token starting 1-7
    # (the real NHS issued range).
    import re

    nhs_real_rx = re.compile(r"\b[1-7]\d{9}\b")
    for enc in fixture["encounters"]:
        match = nhs_real_rx.search(enc["text"])
        assert match is None, (
            f"Synthetic encounter {enc['id']} contains what looks like a real "
            f"NHS number: {match.group(0)}"
        )
