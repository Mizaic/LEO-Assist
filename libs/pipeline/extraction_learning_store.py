"""Persist learned fingerprints and de-identified few-shots.

Atlas trace:
  DI: DI-0C766F85
  DI: DI-4A012A59
  DO: DO-83EB8C56
  DO: DO-E7824FED
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Callable

from libs.cypher.form_learning_queries import (
    LIST_EXTRACTION_FEW_SHOTS,
    LIST_FORM_FINGERPRINTS,
    UPSERT_EXTRACTION_FEW_SHOT,
    UPSERT_FORM_FINGERPRINT,
)
from libs.pipeline.form_fingerprint_registry import register_fingerprint

logger = logging.getLogger(__name__)

_FEW_SHOTS: list[dict[str, Any]] = []
_FEW_LOADED = False
_FEW_LOADER: Callable[[], list[dict[str, Any]]] | None = None
_WRITE_FP: Callable[[str, str], None] | None = None
_WRITE_FS: Callable[[dict[str, Any]], None] | None = None


def reset_learned_few_shots() -> None:
    global _FEW_LOADED, _FEW_LOADER, _WRITE_FP, _WRITE_FS
    _FEW_SHOTS.clear()
    _FEW_LOADED = False
    _FEW_LOADER = _empty_few_shots
    _WRITE_FP = None
    _WRITE_FS = None


def _empty_few_shots() -> list[dict[str, Any]]:
    return []


def set_few_shot_loader(loader: Callable[[], list[dict[str, Any]]]) -> None:
    global _FEW_LOADER, _FEW_LOADED
    _FEW_LOADER = loader
    _FEW_LOADED = False


def set_learning_writers(
    write_fingerprint: Callable[[str, str], None] | None = None,
    write_few_shot: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    global _WRITE_FP, _WRITE_FS
    _WRITE_FP = write_fingerprint
    _WRITE_FS = write_few_shot


def remember_few_shot(example: dict[str, Any]) -> None:
    if not example or not example.get("deidentified"):
        return
    key = (example.get("input"), example.get("output"))
    if any((row.get("input"), row.get("output")) == key for row in _FEW_SHOTS):
        return
    _FEW_SHOTS.append(dict(example))


def learned_few_shots() -> list[dict[str, Any]]:
    global _FEW_LOADED
    if not _FEW_LOADED:
        for row in _safe_few_load():
            remember_few_shot(row)
        _FEW_LOADED = True
    return list(_FEW_SHOTS)


def persist_review_learning(
    *,
    fingerprint_name: str,
    fingerprint: str,
    few_shot: dict[str, Any] | None = None,
    write_fingerprint: Callable[[str, str], None] | None = None,
    write_few_shot: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    register_fingerprint(fingerprint_name, fingerprint)
    payload = dict(few_shot or {})
    remember_few_shot(payload)
    writer_fp = write_fingerprint or _WRITE_FP
    writer_fs = write_few_shot or _WRITE_FS
    if writer_fp:
        writer_fp(fingerprint_name, fingerprint)
    if writer_fs and payload:
        writer_fs(payload)


def load_fingerprint_rows(client: Any) -> list[tuple[str, str]]:
    rows = client.run(LIST_FORM_FINGERPRINTS)
    return [
        (str(row.get("name") or ""), str(row.get("fingerprint") or ""))
        for row in rows or []
        if row.get("name") and row.get("fingerprint")
    ]


def load_few_shot_rows(client: Any) -> list[dict[str, Any]]:
    rows = client.run(LIST_EXTRACTION_FEW_SHOTS)
    return [dict(row) for row in rows or [] if row.get("deidentified")]


def write_fingerprint_row(client: Any, name: str, fingerprint: str) -> None:
    client.run(
        UPSERT_FORM_FINGERPRINT,
        name=name,
        fingerprint=fingerprint,
        source="learned",
    )


def write_few_shot_row(client: Any, few_shot: dict[str, Any]) -> None:
    raw = f"{few_shot.get('input') or ''}\n{few_shot.get('output') or ''}"
    example_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    client.run(
        UPSERT_EXTRACTION_FEW_SHOT,
        example_id=example_id,
        input=str(few_shot.get("input") or ""),
        output=str(few_shot.get("output") or ""),
        category=str(few_shot.get("category") or ""),
        deidentified=bool(few_shot.get("deidentified")),
        fingerprint=str(few_shot.get("fingerprint") or ""),
    )


def _safe_few_load() -> list[dict[str, Any]]:
    if _FEW_LOADER is not None:
        try:
            return list(_FEW_LOADER() or [])
        except Exception:
            return []
    try:
        return _load_few_shots_from_knowledge()
    except Exception:
        logger.warning("Could not load learned few-shots", exc_info=True)
        return []


def _load_few_shots_from_knowledge() -> list[dict[str, Any]]:
    from libs.neo4j_client.client import KnowledgeGraphClient

    client = KnowledgeGraphClient()
    try:
        return load_few_shot_rows(client)
    finally:
        client.close()


def ensure_learning_writers() -> None:
    if _WRITE_FP is not None or _WRITE_FS is not None:
        return
    default_knowledge_writers()


def default_knowledge_writers() -> None:
    """Install writers that MERGE learned nodes on the knowledge graph."""

    def _write_fp(name: str, fingerprint: str) -> None:
        _run_knowledge(write_fingerprint_row, name, fingerprint)

    def _write_fs(few_shot: dict[str, Any]) -> None:
        _run_knowledge(write_few_shot_row, few_shot)

    set_learning_writers(write_fingerprint=_write_fp, write_few_shot=_write_fs)


def _run_knowledge(action: Callable[..., None], *args: Any) -> None:
    from libs.neo4j_client.client import KnowledgeGraphClient

    client = KnowledgeGraphClient()
    try:
        action(client, *args)
    except Exception:
        logger.warning("Could not persist extraction learning", exc_info=True)
    finally:
        client.close()
