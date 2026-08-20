"""In-process registry of known referral form fingerprints.

Atlas trace:
  DI: DI-0C766F85
  DO: DO-83EB8C56
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

_REGISTRY: dict[str, str] = {}
_SEEDED = False
_LEARNED_LOADED = False
_LOADER: Callable[[], list[tuple[str, str]]] | None = None
_SUFFIX = ".fingerprint.txt"


def _empty_rows() -> list[tuple[str, str]]:
    return []


def reset_registry() -> None:
    global _SEEDED, _LEARNED_LOADED, _LOADER
    _REGISTRY.clear()
    _SEEDED = False
    _LEARNED_LOADED = False
    _LOADER = _empty_rows


def set_persisted_loader(loader: Callable[[], list[tuple[str, str]]]) -> None:
    global _LOADER, _LEARNED_LOADED
    _LOADER = loader
    _LEARNED_LOADED = False


def register_fingerprint(name: str, fingerprint: str) -> None:
    if name and fingerprint:
        _REGISTRY[name] = fingerprint


def apply_persisted_fingerprints(rows: list[tuple[str, str]]) -> None:
    for name, fingerprint in rows or []:
        register_fingerprint(name, fingerprint)


def known_fingerprints() -> dict[str, str]:
    global _LEARNED_LOADED
    if not _SEEDED:
        seed_fingerprints()
    if not _LEARNED_LOADED:
        apply_persisted_fingerprints(_safe_load())
        _LEARNED_LOADED = True
    return dict(_REGISTRY)


def _safe_load() -> list[tuple[str, str]]:
    if _LOADER is not None:
        try:
            return list(_LOADER() or [])
        except Exception:
            return []
    try:
        return _load_from_knowledge_graph()
    except Exception:
        return []


def _load_from_knowledge_graph() -> list[tuple[str, str]]:
    from libs.neo4j_client.client import KnowledgeGraphClient
    from libs.pipeline.extraction_learning_store import load_fingerprint_rows

    client = KnowledgeGraphClient()
    try:
        return load_fingerprint_rows(client)
    finally:
        client.close()


def default_templates_root() -> Path:
    return Path(__file__).resolve().parents[2] / "templates"


def _fingerprint_paths(root: Path) -> list[Path]:
    paths = list(root.glob(f"*{_SUFFIX}"))
    nested = root / "fingerprints"
    if nested.is_dir():
        paths.extend(nested.glob(f"*{_SUFFIX}"))
    return sorted({path.resolve() for path in paths})


def seed_fingerprints(root: Path | None = None) -> int:
    """Load ASCII form skeletons and register their fingerprints."""
    global _SEEDED
    from libs.pipeline.document_quality import form_fingerprint

    added = 0
    for path in _fingerprint_paths(root or default_templates_root()):
        text = path.read_text(encoding="ascii", errors="ignore")
        if not text.strip():
            continue
        name = path.name[: -len(_SUFFIX)]
        register_fingerprint(name, form_fingerprint(text))
        added += 1
    _SEEDED = True
    return added
