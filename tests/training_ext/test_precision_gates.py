"""Wave 5 tests for the Neo4j-backed precision gate loader."""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.training_ext.precision_gates import load_precision_gates_from_neo4j


def test_neo4j_rows_override_fallback():
    session = MagicMock()
    session.run.return_value = [
        {"label": "disorder", "min_f1": 0.88},
        {"label": "FINDING", "min_f1": "0.72"},
        {"label": "", "min_f1": 0.5},  # skipped
        {"label": "BAD", "min_f1": "not-a-number"},  # skipped
    ]
    fallback = {"DISORDER": 0.82, "FINDING": 0.78, "PROCEDURE": 0.80}
    merged = load_precision_gates_from_neo4j(fallback, session=session)
    assert merged["DISORDER"] == 0.88  # overridden
    assert merged["FINDING"] == 0.72
    assert merged["PROCEDURE"] == 0.80  # unchanged


def test_neo4j_unavailable_returns_fallback():
    fallback = {"DISORDER": 0.82}
    # No session injected and no client available — returns fallback dict.
    merged = load_precision_gates_from_neo4j(fallback, session=None)
    assert merged["DISORDER"] == 0.82
