"""VT -- gated LEO phone-home to Atlas NCRs.

Atlas: DI-C7DEF132
"""

from __future__ import annotations

from typing import Any

import pytest

from libs.atlas_qms.phone_home import (
    collect_signals,
    digest_phone_home,
    phone_home_escalated,
    preview_phone_home,
    submit_signal,
)
from libs.atlas_qms.phone_home_sig import (
    IssueSignal,
    find_open_ncr,
    ncr_description,
    ncr_title,
    signature_for,
)


def test_escalate_opens_or_reuses_one_open_record() -> None:
    store: list[dict[str, str]] = []

    def list_fn(query: str = "", limit: int = 50) -> list[dict[str, str]]:
        return [
            row
            for row in store
            if query in f"{row.get('title', '')} {row.get('description', '')}"
        ]

    def create_fn(**kwargs: str) -> dict[str, str]:
        row = {
            "id": "n1",
            "title": kwargs["title"],
            "description": kwargs["description"],
            "status": "identified",
        }
        store.append(row)
        return row

    signal = IssueSignal(
        family="hitl_escalated",
        key="low_confidence_coding",
        count=1,
        gate="escalate",
    )
    first = submit_signal(signal, list_fn=list_fn, create_fn=create_fn)
    second = submit_signal(signal, list_fn=list_fn, create_fn=create_fn)
    assert first["action"] == "created"
    assert second["action"] == "exists"
    assert len(store) == 1


def test_below_threshold_does_not_open_record() -> None:
    signals = collect_signals(
        [{"key": "raised psa", "tag": "finding", "count": 19}],
        [{"source": "pipeline_hitl_ner", "key": "ner_false_positive", "count": 3}],
        20,
    )
    assert signals == []


def test_payload_has_signature_count_not_patient_or_letter() -> None:
    signal = IssueSignal(
        family="uncoded_phrase",
        key="nhs 943 476 5919 raised psa in letter",
        count=24,
        gate="threshold",
        tag="patient 1234567890",
    )
    title = ncr_title(signal)
    desc = ncr_description(signal)
    sig = signature_for(signal.family, signal.key)
    assert sig in desc
    assert "Seen: 24 times." in desc
    assert sig.rsplit("|", 1)[-1] in title
    blob = title + desc
    assert "943" not in blob
    assert "5919" not in blob
    assert "1234567890" not in blob
    assert "raised psa" not in blob.lower()
    assert "letter" not in desc.lower()
    assert "No person identifiers." in desc


def test_open_signature_is_reused_closed_is_not() -> None:
    sig = signature_for("hitl_ner", "ner_false_positive")
    open_row = find_open_ncr(
        [{"title": "old", "description": sig, "status": "identified"}],
        sig,
    )
    assert open_row is not None
    closed = find_open_ncr(
        [{"title": "old", "description": sig, "status": "closed"}],
        sig,
    )
    assert closed is None


def test_digest_creates_only_for_gated_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[str] = []

    def fake_run(query: str, **params: Any) -> list[dict[str, Any]]:
        if "UncodedPhrase" in query:
            return [{"key": "raised psa", "tag": "finding", "count": 24}]
        return [
            {"source": "pipeline_hitl_coding", "key": "coding_mismatch", "count": 20}
        ]

    def fake_list(query: str = "", limit: int = 50) -> list[dict[str, Any]]:
        return []

    def fake_create(**kwargs: str) -> dict[str, str]:
        created.append(kwargs["title"])
        return {"id": f"n{len(created)}", "title": kwargs["title"]}

    out = digest_phone_home(
        run=fake_run, list_fn=fake_list, create_fn=fake_create, min_count=20
    )
    assert len(out["results"]) == 2
    assert all(row["action"] == "created" for row in out["results"])
    preview = preview_phone_home(run=fake_run, min_count=20)
    assert preview["threshold"] == 20
    assert len(preview["items"]) == 2


def test_disabled_phone_home_does_not_create(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEO_PHONE_HOME_ENABLED", "0")
    called = {"create": 0}

    def fake_create(**kwargs: str) -> dict[str, str]:
        called["create"] += 1
        return {"id": "n"}

    out = phone_home_escalated(task_type="peer_review")
    assert out["action"] == "disabled"
    assert called["create"] == 0
