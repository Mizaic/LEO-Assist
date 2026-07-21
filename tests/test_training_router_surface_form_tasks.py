"""Surface-form-task and coding-review-resolved routes live in the
training router's sub-modules (2026-07 CTO peer-review item 2: core-api
router decomposition split training.py into per-feature sub-routers).

surface-form-tasks -> app.routers.context_and_ignore_rules
coding-review/resolved -> app.routers.coding_review

Both sub-router APIRouters carry no prefix of their own -- the "/training"
prefix is applied once, by the aggregator in app.routers.training -- so
this test re-applies it locally to assert on the real mounted paths.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock


def _import_sub_routers():
    mocks = {
        "libs.auth.org_scope": MagicMock(
            CallerScope=MagicMock, get_caller_scope=MagicMock()
        ),
        "libs.neo4j_client.client": MagicMock(),
        "libs.cypher.coding_review_queries": MagicMock(),
        "libs.cypher.exclusion_queries": MagicMock(),
        "libs.cypher.surface_form_task_queries": MagicMock(),
        "libs.cypher.post_processor_rule_queries": MagicMock(),
        "libs.ner.schema_mapper": MagicMock(LABEL_TO_SNOMED_TAG={}),
        "libs.terminology.client": MagicMock(),
        "libs.terminology.preferred_terms": MagicMock(),
        "libs.utils.logging": MagicMock(),
        "services.terminology_api.app.queries.terminology": MagicMock(),
        "app.deps": MagicMock(require_admin=MagicMock()),
    }
    for mod, mock in mocks.items():
        sys.modules.setdefault(mod, mock)

    for mod in ("app.routers.context_and_ignore_rules", "app.routers.coding_review"):
        sys.modules.pop(mod, None)

    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))

    from app.routers.coding_review import router as coding_review_router
    from app.routers.context_and_ignore_rules import (
        router as context_and_ignore_rules_router,
    )

    return context_and_ignore_rules_router, coding_review_router


def test_router_includes_surface_form_task_endpoints() -> None:
    rules_router, coding_review_router = _import_sub_routers()
    paths = {f"/training{r.path}" for r in rules_router.routes}
    paths |= {f"/training{r.path}" for r in coding_review_router.routes}
    assert "/training/surface-form-tasks" in paths
    assert "/training/surface-form-tasks/{task_id}" in paths
    assert "/training/coding-review/resolved" in paths
