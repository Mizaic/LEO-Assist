"""A failed lab-config lookup is never read as "no config".

If the Knowledge Graph cannot be asked, the lookup must say so. Before
this fix it returned None, the same answer as "this test has no config",
and cached it for the life of the process, so one outage silently hid
every abnormal-result finding. Rule 2 of fail-closed-boundary.mdc:
Found, NotFound and LookupFailed are three different answers.

Atlas trace:
  DI: DI-B7A69F26 (fail-closed boundary), DI-02AB393F (degraded runs
      routed to human review), DI-9456E5BE (lab result findings)
  DO: DO-AA3B7FCC
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest

from libs.lab_results.classifier import LabConfigUnavailable, get_lab_config
from libs.lab_results.pipeline import enrich_lab_result_findings
from libs.pipeline.form_schema_seeding import seed_ordered_tests_entities
from libs.pipeline_graph.subgraphs.terminology import _resolve_terms
from libs.terminology.client import TerminologyClient
from tests.test_form_schema_single_result_row import (
    FIT_SCHEMA,
    OBSERVABLE_ID,
    PROCEDURE_ID,
    RESULTED_TEXT,
)

_ROW = {
    "concept_id": OBSERVABLE_ID,
    "display_name": "Faecal immunochemical test result",
    "canonical_unit": "ug/g",
    "source": "test",
    "conversions": [],
    "ranges": [],
    "interpretations": [],
}


class _Result:
    def single(self):
        return _ROW


class _Session:
    def run(self, *_args, **_kwargs):
        return _Result()


class _Graph:
    """Knowledge Graph stand-in; ``down`` makes every session fail."""

    down = True

    @contextmanager
    def session(self):
        if _Graph.down:
            raise ConnectionError("graph unreachable")
        yield _Session()

    def close(self):
        return None


@pytest.fixture(autouse=True)
def _graph(monkeypatch):
    _Graph.down = True
    monkeypatch.setattr("libs.lab_results.classifier.KnowledgeGraphClient", _Graph)
    monkeypatch.setattr("libs.lab_results.classifier._CONFIG_CACHE", {})


def test_a_failed_lookup_is_not_no_config():
    with pytest.raises(LabConfigUnavailable):
        get_lab_config(OBSERVABLE_ID)


def test_a_failed_lookup_is_not_cached():
    with pytest.raises(LabConfigUnavailable):
        get_lab_config(OBSERVABLE_ID)
    _Graph.down = False
    config = get_lab_config(OBSERVABLE_ID)
    assert config is not None
    assert config.canonical_unit == "ug/g"


def _seeds() -> list[dict]:
    return seed_ordered_tests_entities(RESULTED_TEXT, FIT_SCHEMA)


def test_the_lab_step_does_not_hide_a_failed_lookup():
    with pytest.raises(LabConfigUnavailable):
        enrich_lab_result_findings(_seeds(), patient_sex=None, patient_age=None)


def test_the_terminology_step_degrades_the_run_when_the_lookup_fails():
    def _no_hits(self, terms, expected_tags=None, org_id=None):
        return {term: [] for term in terms}

    with patch.object(TerminologyClient, "resolve", _no_hits):
        out = _resolve_terms(
            {"entities": _seeds(), "expected_tags": {}, "confidence_threshold": 0.55}
        )
    assert out["degraded"] is True
    assert any(w.startswith("lab_result_lookup_failed") for w in out["warnings"])
    codes = {e.get("concept_id") for e in out["entities"]}
    assert codes == {PROCEDURE_ID, OBSERVABLE_ID}
