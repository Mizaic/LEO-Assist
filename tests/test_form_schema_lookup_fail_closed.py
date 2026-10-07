"""Site 3: a database error must not read as "this form was never taught".

`load_form_schema` returned ``None`` both when the form was genuinely
never taught AND when Neo4j errored.

`.cursor/rules/fail-closed-boundary.mdc` rule 2: "Lookups have three
answers, not two. A resolution lookup returns Found, NotFound, or
LookupFailed. None may only mean definitely not there. It must never
also mean we could not ask."

Clinical consequence: a taught form's checkbox normalisation is skipped
when the database blips. Ticked boxes on a referral form are read as
untouched, so real findings never reach the record.

The candidate lookup used by recognition has the same guarantee; see
tests/test_form_schema_candidates.py and
tests/test_document_chunk_loader_recognition.py.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B7A69F26 (fail-closed boundary for clinical safety layers)
  DI: DI-5C9CA57B (form checkbox normalisation)
  DI: DI-E21DF9EF (form recognition; no hash or service fallback)
  DO: DO-42331CE1
  VT: VT-AA8ED00F
  Risk: R-294446BF
"""

from __future__ import annotations

from typing import Any

import pytest

from libs.pipeline.form_schema_normalizer import FormSchema, FormSection
from libs.pipeline.form_schema_store import (
    FormSchemaWrite,
    _schema_to_sections_json,
    get_cached_schema,
    load_form_schema,
    rebind_form_schema_ids,
    reset_schema_cache,
)

FINGERPRINT = "fingerprint-abc"
ORG_ID = "RK5"
SERVICE_ID = "7980224"


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_schema_cache()
    yield
    reset_schema_cache()


def _schema() -> FormSchema:
    return FormSchema(
        schema_id="seed-1",
        fingerprint=FINGERPRINT,
        form_name="SFH Gynae 2WW",
        sections=[
            FormSection(
                section_id="A",
                section_type="checkbox_multi",
                label="Cancer type",
                start_pattern="Section A: cancer type suspected",
                items=[],
            )
        ],
        created_by="seed",
        status="active",
        organization_id=ORG_ID,
        service_id=SERVICE_ID,
    )


def _row(schema: FormSchema) -> dict[str, Any]:
    return {
        "schema_id": schema.schema_id,
        "fingerprint": schema.fingerprint,
        "form_name": schema.form_name,
        "sections_json": _schema_to_sections_json(schema),
        "chunk_section_map": "[]",
        "created_by": schema.created_by,
        "version": 1,
        "status": schema.status,
        "organization_id": schema.organization_id,
        "service_id": schema.service_id,
    }


class _RaisingClient:
    """Neo4j client stand-in whose every query fails."""

    def run(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        raise ConnectionError("neo4j unreachable")


class _MissClient:
    """Neo4j client stand-in that answers "definitely not there"."""

    def __init__(self) -> None:
        self.calls = 0

    def run(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        self.calls += 1
        return []


class _HitClient:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        self.calls += 1
        return [_row(_schema())]


# ---------------------------------------------------------------------------
# Happy paths -- Found and NotFound must not change
# ---------------------------------------------------------------------------


def test_a_taught_form_is_found() -> None:
    schema = load_form_schema(_HitClient(), FINGERPRINT)
    assert schema is not None
    assert schema.form_name == "SFH Gynae 2WW"


def test_a_form_that_was_never_taught_returns_none() -> None:
    assert load_form_schema(_MissClient(), FINGERPRINT) is None


def test_a_known_miss_is_cached_so_neo4j_is_asked_once() -> None:
    client = _MissClient()
    assert load_form_schema(client, FINGERPRINT) is None
    assert load_form_schema(client, FINGERPRINT) is None
    assert client.calls == 1


def test_a_found_schema_is_cached() -> None:
    client = _HitClient()
    load_form_schema(client, FINGERPRINT)
    load_form_schema(client, FINGERPRINT)
    assert client.calls == 1
    assert get_cached_schema(FINGERPRINT) is not None


# ---------------------------------------------------------------------------
# Site 3 -- LookupFailed is a third answer, never NotFound
# ---------------------------------------------------------------------------


def test_a_database_error_raises_instead_of_returning_none() -> None:
    with pytest.raises(Exception):
        load_form_schema(_RaisingClient(), FINGERPRINT)


def test_a_database_error_is_not_cached_as_a_miss() -> None:
    """A blip must not poison the cache into "never taught" for the process."""
    with pytest.raises(Exception):
        load_form_schema(_RaisingClient(), FINGERPRINT)
    assert get_cached_schema(FINGERPRINT) is None

    recovered = load_form_schema(_HitClient(), FINGERPRINT)
    assert recovered is not None, "a recovered database must find the taught form"


def test_the_lookup_error_says_what_happened_in_plain_english() -> None:
    with pytest.raises(Exception) as excinfo:
        load_form_schema(_RaisingClient(), FINGERPRINT)
    message = str(excinfo.value)
    assert message.isascii()
    assert FINGERPRINT in message
    assert "could not" in message.lower()


def test_a_lookup_error_does_not_overwrite_a_taught_form() -> None:
    """rebind must never re-seed over sections it simply could not read."""
    write = FormSchemaWrite(
        fingerprint=FINGERPRINT,
        form_name="SFH Gynae 2WW",
        sections=[],
        created_by="seed",
        organization_id=ORG_ID,
        service_id=SERVICE_ID,
    )
    with pytest.raises(Exception):
        rebind_form_schema_ids(_RaisingClient(), write)
