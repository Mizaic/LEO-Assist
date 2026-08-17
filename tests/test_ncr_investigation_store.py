"""VT -- Local NCR investigation keeps identifiers. Atlas notes are redacted.

Atlas: DI-ED5A9AC3
"""

from __future__ import annotations

import json
from typing import Any

from libs.atlas_qms.investigation_store import load_investigation, log_event, save_cases
from libs.atlas_qms.ncr_client import NcrClientError
from libs.cypher.ncr_investigation_queries import ADD_EVENT, SAVE_CASES


def test_save_cases_keeps_nhs_and_ubrn_locally() -> None:
    stored: dict[str, Any] = {}

    def run(query: str, **params: Any) -> list[dict[str, Any]]:
        stored["query"] = query
        stored["params"] = params
        return [{"nc_id": params["nc_id"], "cases_json": params["cases_json"]}]

    row = save_cases(
        "nc-1",
        [
            {
                "run_id": "run-9",
                "patient_id": "p1",
                "patient_name": "A",
                "nhs_number": "9434765919",
                "ubrn": "000012345678",
                "status": "done",
            }
        ],
        run=run,
    )
    assert stored["query"] == SAVE_CASES
    assert "9434765919" in stored["params"]["cases_json"]
    assert "000012345678" in stored["params"]["cases_json"]
    assert row["cases"][0]["nhs_number"] == "9434765919"


def test_load_investigation_returns_local_cases() -> None:
    def run(query: str, **params: Any) -> list[dict[str, Any]]:
        if "HAS_EVENT" in query:
            return []
        return [
            {
                "nc_id": "nc-1",
                "title": "Missed",
                "cases_json": json.dumps(
                    [{"run_id": "r1", "nhs_number": "9434765919", "ubrn": ""}]
                ),
            }
        ]

    loaded = load_investigation("nc-1", run=run)
    assert loaded["cases"][0]["nhs_number"] == "9434765919"


def test_log_event_sends_redacted_atlas_text() -> None:
    sent: dict[str, str] = {}
    stored: dict[str, Any] = {}

    def comment(nc_id: str, text: str) -> dict[str, str]:
        sent["nc_id"] = nc_id
        sent["text"] = text
        return {"ok": "true"}

    def run(query: str, **params: Any) -> list[dict[str, Any]]:
        stored["query"] = query
        stored["params"] = params
        return [
            {
                "event_id": "e1",
                "atlas_ok": True,
                "atlas_text": params["atlas_text"],
            }
        ]

    row = log_event(
        "nc-1",
        "review_opened",
        "Opened NHS 943 476 5919. Local run run-9.",
        run=run,
        comment=comment,
    )
    assert stored["query"] == ADD_EVENT
    assert stored["params"]["local_text"].startswith("Opened NHS")
    assert "943" not in sent["text"]
    assert "[NHS_NUMBER]" in sent["text"]
    assert row["atlas_ok"] is True


def test_log_event_keeps_local_when_atlas_fails() -> None:
    def comment(_nc_id: str, _text: str) -> dict[str, str]:
        raise NcrClientError("down")

    def run(query: str, **params: Any) -> list[dict[str, Any]]:
        return [
            {
                "event_id": "e2",
                "atlas_ok": params["atlas_ok"],
                "atlas_text": params["atlas_text"],
            }
        ]

    row = log_event("nc-1", "case_added", "Added a case.", run=run, comment=comment)
    assert row["atlas_ok"] is False
