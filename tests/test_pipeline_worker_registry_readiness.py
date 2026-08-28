"""A worker that cannot assemble the pipeline must not report itself healthy.

``fail-closed-boundary.mdc`` rule 5 says a subgraph that fails to register
aborts worker startup, and is never quietly missing from the assembled
pipeline at run time.

Half of that already holds. ``_register_defaults`` is all-or-nothing and
``_default_registry`` is only assigned once registration completes, so no run
can execute a pipeline with a subgraph silently missing -- every run raises
instead. That is the clinically important half.

The other half did not hold. Registry warm-up runs in a daemon thread whose
handler logged "Registry warm-up failed (non-fatal)", so the worker booted,
reported ``/health`` ok, and accepted referrals it could not process. Every
one of them then failed. Nothing a person watches said the worker was unfit,
which is the same "a log line is not visible" problem rule 1 names.

Killing the process from a daemon thread would need ``os._exit``, which loses
in-flight work. Reporting unfit through the health endpoint is what
orchestration already acts on, so that is what this pins.

Atlas trace:
  DI: DI-B7A69F26  (fail-closed boundary)
  Risk: R-294446BF
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_registry_state():
    """Registry readiness is module state; put it back after each test."""
    from services.pipeline_worker.app import main

    before = main.registry_health()
    yield
    main.set_registry_health(ready=before["ready"], detail=before["detail"])


def test_a_fresh_worker_has_not_yet_proved_the_registry() -> None:
    """Unknown is not the same as broken, and must not read as broken."""
    from services.pipeline_worker.app import main

    main.set_registry_health(ready=None, detail="")

    assert main.registry_health()["ready"] is None
    assert main.registry_is_unfit() is False


def test_a_registered_registry_is_fit() -> None:
    from services.pipeline_worker.app import main

    main.set_registry_health(ready=True, detail="30 subgraphs")

    assert main.registry_is_unfit() is False


def test_a_failed_registry_makes_the_worker_unfit() -> None:
    """The whole point: a worker that cannot build the pipeline says so."""
    from services.pipeline_worker.app import main

    main.set_registry_health(ready=False, detail="No module named 'x'")

    assert main.registry_is_unfit() is True


def test_health_reports_503_when_the_registry_failed() -> None:
    """Orchestration acts on the status code, not on the log."""
    import asyncio

    from fastapi import HTTPException

    from services.pipeline_worker.app import main

    main.set_registry_health(ready=False, detail="No module named 'x'")

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(main.health())

    assert excinfo.value.status_code == 503


def test_health_says_what_is_wrong_in_words_a_person_can_read() -> None:
    from services.pipeline_worker.app import main

    main.set_registry_health(ready=False, detail="No module named 'x'")

    detail = main.registry_health()["detail"]
    assert "No module named 'x'" in detail


def test_health_is_ok_once_the_registry_is_ready() -> None:
    import asyncio

    from services.pipeline_worker.app import main

    main.set_registry_health(ready=True, detail="30 subgraphs")

    payload = asyncio.run(main.health())

    assert payload["status"] == "ok"
    assert payload["service"] == "pipeline-worker"


def test_a_missing_required_subgraph_makes_the_worker_unfit() -> None:
    """snomed_enrichment absent used to log an error and carry on."""
    from services.pipeline_worker.app import main

    main.set_registry_health(
        ready=False, detail="required subgraph 'snomed_enrichment' is not registered"
    )

    assert main.registry_is_unfit() is True
