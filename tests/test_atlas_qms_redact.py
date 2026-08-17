"""VT -- Redact NHS numbers and referral numbers before Atlas send.

Atlas: DI-ED5A9AC3
"""

from __future__ import annotations

import pytest

from libs.atlas_qms.ncr_client import (
    NcrClientError,
    add_product_ncr_comment,
    safe_atlas_text,
)
from libs.atlas_qms.ncr_shape import validate_ncr_create
from libs.atlas_qms.redact import contains_identifiers, redact_for_atlas


def test_redact_replaces_nhs_and_ubrn() -> None:
    text = redact_for_atlas("NHS 943 476 5919 and UBRN 0000 1234 5678 opened a review.")
    assert "[NHS_NUMBER]" in text
    assert "[UBRN]" in text
    assert "943" not in text
    assert "000012345678" not in text.replace(" ", "")
    assert not contains_identifiers(text)


def test_redact_replaces_compact_twelve_digit_ubrn() -> None:
    text = redact_for_atlas("Referral 000012345678")
    assert "[UBRN]" in text
    assert "000012345678" not in text


def test_validate_create_redacts_identifiers() -> None:
    row = validate_ncr_create(
        title="Missed code for 9434765919",
        description="UBRN 000012345678 failed a letter check.",
        severity="minor",
    )
    assert "[NHS_NUMBER]" in row["title"]
    assert "9434765919" not in row["title"]
    assert "[UBRN]" in row["description"]
    assert "000012345678" not in row["description"]


def test_safe_atlas_text_rejects_if_redact_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("libs.atlas_qms.ncr_client.redact_for_atlas", lambda text: text)
    with pytest.raises(NcrClientError, match="patient number"):
        safe_atlas_text("9434765919")


def test_update_ncr_redacts_description(monkeypatch: pytest.MonkeyPatch) -> None:
    from libs.atlas_qms.ncr_client import update_product_ncr

    captured: dict[str, object] = {}

    def fake_request(method: str, path: str, body: dict | None = None) -> dict:
        captured["method"] = method
        captured["path"] = path
        captured["body"] = body
        return {"id": "nc-1", "title": "Missed", "description": body["description"]}

    monkeypatch.setattr("libs.atlas_qms.ncr_client._request", fake_request)
    update_product_ncr("nc-1", description="Case NHS 9434765919")
    assert captured["method"] == "PATCH"
    assert captured["path"] == "/non-conformances/nc-1"
    body = captured["body"]
    assert isinstance(body, dict)
    assert "9434765919" not in str(body["description"])
    assert "[NHS_NUMBER]" in str(body["description"])


def test_add_comment_sends_redacted_text(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_request(method: str, path: str, body: dict | None = None) -> dict:
        captured["method"] = method
        captured["path"] = path
        captured["body"] = body
        return {"id": "note-1"}

    monkeypatch.setattr("libs.atlas_qms.ncr_client._request", fake_request)
    add_product_ncr_comment("nc-1", "Opened NHS 943 476 5919")
    assert captured["method"] == "POST"
    assert captured["path"] == "/non-conformances/nc-1/comments"
    body = captured["body"]
    assert isinstance(body, dict)
    assert "[NHS_NUMBER]" in str(body["text"])
    assert "943" not in str(body["text"])
