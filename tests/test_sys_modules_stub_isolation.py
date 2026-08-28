"""Guard against test modules that leave a fake in ``sys.modules``.

A test module that runs::

    sys.modules.setdefault("app.db.neo4j_client", MagicMock(...))

at import time creates an inconsistent import graph. The real submodule
is never imported, so the parent package object never gets the
``neo4j_client`` attribute set on it. ``importlib.import_module`` still
succeeds, because it finds the fake in the cache and returns it without
touching the parent.

That combination is what breaks a later test. ``monkeypatch.setattr``
resolves a dotted target by walking attributes, falling back to
``import_module`` only to trigger the import. The import reports
success, the attribute walk then fails, and the victim dies with::

    AttributeError: 'module' object at app.db.neo4j_client
                    has no attribute 'neo4j_client'

Because the stub runs at *collection* time and is never restored, the
victim fails whenever the two modules are collected together, and
passes when run alone. That made regression runs report the code as
healthier than it was.

This guard fails the moment any first-party submodule is reachable via
``sys.modules`` but missing from its parent package, so the defect
cannot be reintroduced without a red test.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from types import ModuleType
from typing import Iterator
from unittest.mock import MagicMock

_FIRST_PARTY_PREFIXES = ("app.", "libs.", "services.")

_MISSING = object()


def dangling_submodule_stubs() -> list[str]:
    """Return first-party ``sys.modules`` keys their parent does not expose.

    A same-name re-export (``libs.guidelines`` exposing the function
    ``action_already_done`` rather than the module of that name) is a
    normal Python pattern and is deliberately not reported: the
    attribute resolves, so no dotted-path lookup breaks.
    """
    dangling: list[str] = []
    for name, module in sorted(sys.modules.items()):
        if module is None or "." not in name:
            continue
        if not name.startswith(_FIRST_PARTY_PREFIXES):
            continue
        parent_name, _, leaf = name.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is None:
            continue
        if getattr(parent, leaf, _MISSING) is _MISSING:
            dangling.append(name)
    return dangling


def test_no_first_party_module_is_stubbed_without_its_parent() -> None:
    """No test may leave a first-party module unreachable from its parent."""
    dangling = dangling_submodule_stubs()
    assert dangling == [], (
        "These modules are in sys.modules but missing from their parent "
        "package, so monkeypatch.setattr on a dotted path through them "
        "will fail in a later test: "
        + ", ".join(dangling)
        + ". A test module most likely called sys.modules.setdefault(...) "
        "at import time. Import the real module instead, or patch the "
        "attribute you need inside the test with monkeypatch."
    )


@contextmanager
def _stubbed_package() -> Iterator[str]:
    """Install a fake parent package plus a dangling child, then remove it."""
    parent = "leo_guard_fixture_pkg"
    child = f"{parent}.child"
    sys.modules[parent] = ModuleType(parent)
    sys.modules[child] = MagicMock()
    try:
        yield child
    finally:
        sys.modules.pop(child, None)
        sys.modules.pop(parent, None)


def test_detector_catches_the_pattern_it_guards_against() -> None:
    """Prove the guard has teeth, so a green run means something."""
    global _FIRST_PARTY_PREFIXES
    original = _FIRST_PARTY_PREFIXES
    with _stubbed_package() as child:
        _FIRST_PARTY_PREFIXES = original + ("leo_guard_fixture_pkg.",)
        try:
            assert child in dangling_submodule_stubs()
        finally:
            _FIRST_PARTY_PREFIXES = original
    assert child not in sys.modules
