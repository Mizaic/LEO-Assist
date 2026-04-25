"""Live VT: segmenter must create separate windows for a multi-site patient.

Regression target for W-018 (compliance/coverage-waivers.md):

  Patient 9990001004 has THREE distinct cancer investigation pathways:
    - Lung     : June-July 2025, GP-initiated chest X-ray, benign result July 16
    - Breast   : August 2025+, 2WW referral August 12, treatment ongoing
    - Upper GI : August 2025+, 2WW referral August 12, first_seen August 27

  Before the segmenter fix, the engine produced only 2 episode windows
  (Breast + one merged window), making it impossible for the milestone
  extractor to attach Lung and Upper GI milestones to separate episodes.

  This VT gates the fix by asserting the segmenter creates >= 3 windows
  with at least one Breast, one Lung, and one upper-GI-type site.

Atlas trace:
  DI: DI-7FF67ECE  (episode window segmentation requirement)
  W-018 waiver cleared when this test is green.

Gated: set RUN_EPISODE_ENGINE_GOLD_VT=1 to run (makes live LLM + Neo4j calls).
"""

from __future__ import annotations

import os
from datetime import date

import pytest

_MULTI_SITE_PATIENT = "9990001004"

_GATED = pytest.mark.skipif(
    os.getenv("RUN_EPISODE_ENGINE_GOLD_VT") != "1",
    reason=(
        "Live LLM + Neo4j segmenter VT (~$0.05, ~1 min). "
        "Set RUN_EPISODE_ENGINE_GOLD_VT=1 to run."
    ),
)

# Upper GI referrals may be classified as any of these NCDA sites.
_UPPER_GI_SITES = frozenset(
    {"Oesophageal", "Stomach", "Pancreatic", "Liver", "Gallbladder", "Other"}
)


@_GATED
def test_segmenter_multisite_three_windows():
    """Segmenter creates >= 3 windows including Breast, Lung, and an upper-GI site.

    Acceptance criteria (W-018 clearance):
    1. >= 3 candidate windows returned.
    2. 'Breast' is one of the suspected sites.
    3. 'Lung' is one of the suspected sites (GP-only investigation, no 2WW).
    4. At least one upper-GI site (Oesophageal / Stomach / Pancreatic / etc.)
       is one of the suspected sites.
    """
    from libs.llm_client.factory import create_llm
    from libs.neo4j_client.client import PatientGraphClient
    from services.analysis_worker.app.episode_engine.agents import (
        segmenter as segmenter_agent,
    )
    from services.analysis_worker.app.episode_engine.timeline_loader import (
        load_timeline,
    )

    client = PatientGraphClient()
    try:
        trunk, _, _ = load_timeline(_MULTI_SITE_PATIENT, client=client)
    finally:
        client.close()

    llm = create_llm(provider="aws", tier="small")
    result, trace = segmenter_agent.run(
        llm=llm,
        patient_id=_MULTI_SITE_PATIENT,
        timeline_text=trunk,
    )

    sites = {w.suspected_site for w in result.windows}
    count = len(result.windows)

    print(f"\nSegmenter: {count} window(s) -- sites: {sites}")
    for w in result.windows:
        end = w.window_end or "open"
        print(f"  {w.window_id}: {w.suspected_site}  {w.window_start} -> {end}")
        print(f"    {w.rationale}")

    assert count >= 3, (
        f"W-018: expected >= 3 windows (Breast + Lung + Upper GI), "
        f"got {count}: {sites}"
    )
    assert "Breast" in sites, (
        f"W-018: missing Breast window -- got: {sites}"
    )
    assert "Lung" in sites, (
        f"W-018: missing Lung window (GP-only chest X-ray investigation) -- "
        f"the new GP-ONLY INVESTIGATION WINDOWS heuristic should detect this "
        f"even without a 2WW referral -- got: {sites}"
    )
    upper_gi_present = bool(sites & _UPPER_GI_SITES)
    assert upper_gi_present, (
        f"W-018: missing upper-GI window (expected one of {_UPPER_GI_SITES})"
        f" -- SAME-DAY MULTI-SITE 2WW heuristic should emit a separate window"
        f" for the upper-GI 2WW referral on the same day as Breast"
        f" -- got: {sites}"
    )


@_GATED
def test_segmenter_lung_window_closed():
    """Lung window must have window_end (benign pathway, closed July 2025).

    The Lung investigation resolved as benign on 2025-07-16. The segmenter
    should close that window (set window_end) rather than leaving it open-ended.
    """
    from libs.llm_client.factory import create_llm
    from libs.neo4j_client.client import PatientGraphClient
    from services.analysis_worker.app.episode_engine.agents import (
        segmenter as segmenter_agent,
    )
    from services.analysis_worker.app.episode_engine.timeline_loader import (
        load_timeline,
    )

    client = PatientGraphClient()
    try:
        trunk, _, _ = load_timeline(_MULTI_SITE_PATIENT, client=client)
    finally:
        client.close()

    llm = create_llm(provider="aws", tier="small")
    result, _ = segmenter_agent.run(
        llm=llm,
        patient_id=_MULTI_SITE_PATIENT,
        timeline_text=trunk,
    )

    lung_windows = [w for w in result.windows if w.suspected_site == "Lung"]
    assert lung_windows, (
        "Lung window not found -- run test_segmenter_multisite_three_windows first"
    )

    lung = lung_windows[0]
    assert lung.window_end is not None, (
        f"Lung window should be closed (benign result 2025-07-16) "
        f"but window_end is None -- rationale: {lung.rationale}"
    )
    assert lung.window_end <= date(2025, 8, 1), (
        f"Lung window_end {lung.window_end} should be on or before "
        f"2025-08-01 (benign result was on 2025-07-16)"
    )
