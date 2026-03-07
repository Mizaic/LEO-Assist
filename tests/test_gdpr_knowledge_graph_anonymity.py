from __future__ import annotations

from services.terminology_api.app.queries import terminology as tq


def test_surface_form_queries_do_not_store_user_identifiers() -> None:
    joined = "\n".join(
        [
            tq.UPSERT_SURFACE_FORMS,
            tq.UPSERT_SURFACE_FORM_MAPPING,
            tq.APPROVE_SURFACE_FORM,
            tq.LIST_SURFACE_FORMS,
            tq.GROUPED_SURFACE_FORMS,
        ]
    )
    assert "approved_by" not in joined
    assert "created_by" not in joined


def test_surface_form_queries_keep_provenance() -> None:
    assert "provenance" in tq.UPSERT_SURFACE_FORMS
    assert "provenance" in tq.UPSERT_SURFACE_FORM_MAPPING

