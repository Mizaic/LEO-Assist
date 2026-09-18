"""Live persist: add PCB to the taught SFH gynae FormSchema.

Opt-in:

  LIVE_NEO4J_FORM_SCHEMA=1 pytest tests/test_sfh_gynae_pcb_live_persist.py -v

Does not overwrite taught sections. Only merges the completeness member.

Atlas: DI-50BE367C / DI-26546721 / VT-8426C84D
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from libs.completeness.logic_groups import collect_concept_ids
from libs.completeness.schema import add_optional_concept_member
from libs.neo4j_client.client import PatientGraphClient
from libs.pipeline.form_schema_store import (
    FormSchemaWrite,
    reset_schema_cache,
    resolve_form_schema,
    save_form_schema,
)

pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_NEO4J_FORM_SCHEMA") != "1",
    reason="Set LIVE_NEO4J_FORM_SCHEMA=1 to write the taught PCB member.",
)

_PCB_ID = 48880000
_FINGERPRINT = "sfh-gynae-2ww-v1"
_ORG = "RK5"
_SERVICE = "7980224"


@pytest.fixture(scope="module")
def pg_client():
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / "secrets" / ".env.config", override=True)
    load_dotenv(root / "secrets" / ".env", override=False)
    load_dotenv(root / ".env", override=False)
    client = PatientGraphClient()
    yield client
    client.close()


def test_persist_pcb_completeness_member(pg_client) -> None:
    reset_schema_cache()
    schema = resolve_form_schema(
        pg_client,
        _FINGERPRINT,
        organization_id=_ORG,
        service_id=_SERVICE,
    )
    assert schema is not None, "Taught SFH gynae FormSchema missing"
    groups = add_optional_concept_member(
        schema.completeness_groups,
        name="Postcoital bleeding",
        concept_id=_PCB_ID,
        after_name="Postmenopausal bleeding",
    )
    assert _PCB_ID in collect_concept_ids(groups)
    saved = save_form_schema(
        pg_client,
        FormSchemaWrite(
            fingerprint=schema.fingerprint,
            form_name=schema.form_name,
            sections=schema.sections,
            created_by="live_persist_pytest",
            schema_id=schema.schema_id,
            status=schema.status,
            organization_id=schema.organization_id,
            service_id=schema.service_id,
            organization_name=schema.organization_name,
            service_name=schema.service_name,
            organization_ods_code=schema.organization_ods_code,
            completeness_groups=groups,
            prompt_contract=schema.prompt_contract,
        ),
    )
    reset_schema_cache()
    reloaded = resolve_form_schema(
        pg_client,
        saved.fingerprint,
        organization_id=saved.organization_id,
        service_id=saved.service_id,
    )
    assert reloaded is not None
    assert _PCB_ID in collect_concept_ids(reloaded.completeness_groups)
    assert [s.section_id for s in reloaded.sections] == [
        s.section_id for s in schema.sections
    ]
