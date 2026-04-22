"""Live-graph integration test for the v2 detector normaliser.

Atlas trace:
  DI: DI-8A5FCF4F (Defence-in-depth episode detector)

Gated on ``LIVE_NEO4J=1`` so the unit-test sweep stays hermetic. To
run::

    LIVE_NEO4J=1 python -m pytest \\
        tests/episode_detector_v2/test_normaliser_live_neo4j.py -v

The test exercises the schema-binding layer that the synthetic-row
tests deliberately bypass. It runs against the manually-reviewed seed
patient 4920262426 (three pathways: Breast confirmed, Upper GI in-
review, Lung benign-closure) and asserts:

1. ``load_timeline`` returns a non-empty deterministic timeline.
2. The breast 2WW referral SNOMED is promoted to a referral_form.
3. The end-to-end ``build_episodes`` runner returns at least one
   resolved episode for the breast pathway when run against the live
   graph.

The test does **not** assert the full v2 output is equal to the
manual ground truth -- that gap is the subject of the in-flight
shadow-run analysis. It only asserts the schema-binding layer is
plumbed correctly, so we never again ship a detector that returns
zero events because the property name is wrong.
"""

from __future__ import annotations

import asyncio
import os

import pytest

LIVE = os.environ.get("LIVE_NEO4J") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE,
    reason="LIVE_NEO4J=1 not set; skipping real-graph integration test",
)


SEED_PATIENT_ID = "4920262426"
BREAST_REFERRAL_CONCEPT = "276341000000100"


def _client_with_writes_blocked():
    """Wrap PatientGraphClient so MERGE / CREATE / SET / DELETE no-op."""
    from libs.keyvault.loader import load_keyvault_secrets
    from libs.neo4j_client.client import PatientGraphClient

    load_keyvault_secrets()
    inner = PatientGraphClient()

    write_tokens = ("MERGE", "CREATE", "SET", "DELETE", "DETACH", "REMOVE")

    class _ReadOnly:
        def __init__(self, inner):
            self._inner = inner
            self.writes = 0

        def run(self, cypher, **params):
            head = cypher.lstrip().upper()
            if any(tok in head for tok in write_tokens):
                self.writes += 1
                return []
            return self._inner.run(cypher, **params)

        def session(self):
            return self._inner.session()

        def close(self):
            return self._inner.close() if hasattr(self._inner, "close") else None

    return _ReadOnly(inner)


def test_load_timeline_returns_non_empty_for_seed_patient():
    from services.analysis_worker.app.episode_detector_v2.normaliser import (
        load_timeline,
    )

    client = _client_with_writes_blocked()
    try:
        events = asyncio.run(load_timeline(SEED_PATIENT_ID, client))
    finally:
        client.close()

    assert len(events) > 100, (
        "Expected the seed patient's 316-encounter timeline to load; got "
        f"{len(events)} events. Check the live-graph schema binding."
    )
    encounter_ids = {e.encounter_id for e in events}
    assert all(eid for eid in encounter_ids), (
        "Every event must carry a non-empty encounter_id"
    )


def test_load_timeline_promotes_breast_2ww_to_referral_form():
    from services.analysis_worker.app.episode_detector_v2.normaliser import (
        load_timeline,
    )

    client = _client_with_writes_blocked()
    try:
        events = asyncio.run(load_timeline(SEED_PATIENT_ID, client))
    finally:
        client.close()

    breast_referrals = [
        e for e in events
        if e.referral_form
        and e.referral_form.get("form_type") == "2ww_breast"
    ]
    assert breast_referrals, (
        "No encounter in the seed patient's timeline was tagged with a "
        "breast 2WW referral_form; the referral SNOMED registry is "
        "incomplete or the normaliser failed to promote it."
    )


def test_build_episodes_proposes_at_least_one_breast_episode():
    from services.analysis_worker.app.episode_detector_v2.runner import (
        build_episodes,
    )

    client = _client_with_writes_blocked()
    try:
        result = asyncio.run(
            build_episodes(
                patient_id=SEED_PATIENT_ID,
                anchors=None,
                patient_client=client,
                domain_id="",
            )
        )
    finally:
        client.close()

    assert result.coverage_report is not None, (
        "Coverage report must be populated even when the detector "
        "produces zero auto-publish episodes"
    )
    # Breast is the only auto-eligible site as of v1; the seed patient
    # is the canonical breast-confirmed exemplar, so at least one auto
    # episode is expected. If this regresses, investigate the breast
    # signal extractors before relaxing this assertion.
    assert result.episodes_created >= 1, (
        "Expected at least one auto-published breast episode for seed "
        f"patient; got {result.episodes_created}. coverage_report: "
        f"in_episodes={len(result.coverage_report.encounter_ids_in_episodes)}, "
        f"unaccounted={len(result.coverage_report.encounter_ids_unaccounted)}"
    )
