"""Load the taught forms a referral document may be recognised against.

The candidates are every active form taught for the referral's
organisation, plus national forms such as e-RS Clinical Information.
Another organisation's forms are never candidates (tenant isolation).

Three answers, never two (fail-closed rule 2):

- a list of forms, possibly empty, when the graph answered;
- FormSchemaLookupError when the graph could not be asked.

A stored form that cannot be parsed is left out. Its documents then come
back unrecognised and the run pauses for a person, which is visible.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5. Risk R-B88CCFD6.
"""

from __future__ import annotations

import logging
from typing import Any

from libs.cypher.form_schema_queries import LIST_ACTIVE_FORM_SCHEMAS_FOR_ORG
from libs.pipeline.form_schema_normalizer import FormSchema
from libs.pipeline.form_schema_store import _lookup_failed, _record_to_schema

logger = logging.getLogger(__name__)


def _parse(row: dict[str, Any]) -> FormSchema | None:
    try:
        return _record_to_schema(row)
    except Exception:
        logger.warning(
            "Stored FormSchema %s is unusable; it is not a candidate",
            row.get("fingerprint"),
            exc_info=True,
        )
        return None


def load_candidate_schemas(client: Any, organization_id: str) -> list[FormSchema]:
    """Return active taught forms for *organization_id* plus national forms."""
    org = (organization_id or "").strip()
    try:
        rows = client.run(LIST_ACTIVE_FORM_SCHEMAS_FOR_ORG, organization_id=org)
    except Exception as exc:
        logger.warning("FormSchema candidate lookup failed", exc_info=True)
        raise _lookup_failed(f"organisation {org or '(none)'}", exc) from exc
    parsed = (_parse(dict(row)) for row in rows or [])
    return [schema for schema in parsed if schema is not None]
