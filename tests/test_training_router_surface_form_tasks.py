from __future__ import annotations

import sys
from unittest.mock import MagicMock


def _import_router():
    mocks = {
        "libs.auth.org_scope": MagicMock(
            CallerScope=MagicMock, get_caller_scope=MagicMock()
        ),
        "libs.neo4j_client.client": MagicMock(),
        "libs.cypher.training_label_queries": MagicMock(),
        "libs.cypher.coding_review_queries": MagicMock(),
        "libs.cypher.label_verification_queries": MagicMock(),
        "libs.cypher.post_processor_rule_queries": MagicMock(),
        "services.terminology_api.app.queries.terminology": MagicMock(),
        "libs.ner.schema_mapper": MagicMock(LABEL_TO_SNOMED_TAG={}),
        "libs.ner.training_label_writer": MagicMock(),
        "libs.utils.logging": MagicMock(),
        "libs.llm_client.escalation": MagicMock(),
        "app.services.label_verifier": MagicMock(),
        "app.deps": MagicMock(require_admin=MagicMock()),
        "libs.cypher.training_candidate_queries": MagicMock(),
        "libs.cypher.gold_label_queries": MagicMock(),
        "libs.cypher.surface_form_task_queries": MagicMock(),
    }
    for mod, mock in mocks.items():
        sys.modules.setdefault(mod, mock)
    sys.modules.pop("app.routers.training", None)
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))
    from app.routers.training import router

    return router


def test_router_includes_surface_form_task_endpoints() -> None:
    router = _import_router()
    paths = {r.path for r in router.routes}
    assert "/training/surface-form-tasks" in paths
    assert "/training/surface-form-tasks/{task_id}" in paths
    assert "/training/coding-review/resolved" in paths
