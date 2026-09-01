"""Safely force-reseed PromptConfig rows in the Knowledge Graph.

Atlas trace:
  DI: DI-7B978C0C
  DO: DO-FA8FCECF
  VT: VT-06157CF6

The command is read-only unless both ``--apply`` and the confirmation
token are supplied. Before any write it exports every PromptConfig row.
If apply or verification fails, the exported rows are restored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from libs.cypher.prompt_config_queries import FORCE_UPSERT_SEED_PROMPT
from scripts.seed_prompt_configs import SEED_PROMPTS, _get_driver

logger = logging.getLogger(__name__)
CONFIRM_TOKEN = "FORCE_PROMPT_RESEED"
_ROOT = Path(__file__).resolve().parent.parent
_BACKUP_DIR = _ROOT / "artifacts" / "prompt-config-backups"

_SNAPSHOT_QUERY = """
MATCH (p:PromptConfig)
RETURN p.id AS id, p.name AS name, p.version AS version,
       p.description AS description, p.system_prompt AS system_prompt,
       p.output_schema AS output_schema, p.verification AS verification,
       p.few_shot_examples AS few_shot_examples,
       p.max_few_shot AS max_few_shot, p.source AS source
ORDER BY p.name, p.version
"""

_RESTORE_QUERY = """
MERGE (p:PromptConfig {name: $name, version: $version})
SET p.id = $id,
    p.description = $description,
    p.system_prompt = $system_prompt,
    p.output_schema = $output_schema,
    p.verification = $verification,
    p.few_shot_examples = $few_shot_examples,
    p.max_few_shot = $max_few_shot,
    p.source = $source,
    p.updated_at = datetime()
"""


def _canonical(value: Any) -> str:
    """Return stable JSON for hashing prompt content."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            pass
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def prompt_hash(row: dict[str, Any]) -> str:
    """Hash fields that define runtime prompt behavior."""
    payload = {
        "system_prompt": row.get("system_prompt") or "",
        "output_schema": _canonical(row.get("output_schema") or "{}"),
        "few_shot_examples": _canonical(row.get("few_shot_examples") or "[]"),
        "max_few_shot": int(row.get("max_few_shot") or 0),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _seed_row(prompt: dict[str, Any]) -> dict[str, Any]:
    """Convert one source seed into the stored row shape."""
    return {
        "name": prompt["name"],
        "version": int(prompt["version"]),
        "description": prompt.get("description", ""),
        "system_prompt": prompt["system_prompt"],
        "output_schema": prompt.get("output_schema", "{}"),
        "verification": bool(prompt.get("verification", False)),
        "few_shot_examples": prompt.get("few_shot_examples", []),
        "max_few_shot": int(prompt.get("max_few_shot", 0)),
        "source": "seed",
    }


def _record_dict(record: Any) -> dict[str, Any]:
    """Normalise a Neo4j record or mapping."""
    return dict(record.data() if hasattr(record, "data") else record)


def snapshot(session: Any) -> list[dict[str, Any]]:
    """Read all PromptConfig rows without patient data."""
    return [_record_dict(row) for row in session.run(_SNAPSHOT_QUERY)]


def _source_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        source = str(row.get("source") or "unknown")
        counts[source] = counts.get(source, 0) + 1
    return counts


def _redacted_target() -> str:
    uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI") or os.getenv("NEO4J_URI", "")
    parsed = urlsplit(uri)
    return parsed.hostname or "<unset>"


def _diff(
    current: list[dict[str, Any]], seeds: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    existing = {
        (r["name"], int(r["version"])): r
        for r in current
        if r.get("version") is not None
    }
    changes: list[dict[str, Any]] = []
    for seed in seeds:
        key = (seed["name"], int(seed["version"]))
        old = existing.get(key)
        old_hash = prompt_hash(old) if old else None
        new_hash = prompt_hash(seed)
        if old_hash != new_hash or (old and old.get("source") != "seed"):
            changes.append(
                {
                    "name": key[0],
                    "version": key[1],
                    "source": old.get("source") if old else None,
                    "old_hash": old_hash,
                    "new_hash": new_hash,
                }
            )
    return changes


def _write_backup(rows: list[dict[str, Any]], path: Path | None = None) -> Path:
    target = path or _BACKUP_DIR / (
        "prompt-config-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rows, indent=2, ensure_ascii=True), encoding="utf-8")
    return target


def _upsert_seed(session: Any, prompt: dict[str, Any]) -> None:
    row = _seed_row(prompt)
    params = dict(row)
    params["id"] = str(uuid.uuid4())
    params["few_shot_examples"] = json.dumps(
        row["few_shot_examples"], ensure_ascii=True
    )
    session.run(FORCE_UPSERT_SEED_PROMPT, **params).consume()


def restore(session: Any, rows: list[dict[str, Any]]) -> None:
    """Restore every backed-up row after a failed apply."""
    for row in rows:
        if row.get("version") is None:
            continue
        session.run(_RESTORE_QUERY, **row).consume()


def _verify(session: Any, expected: list[dict[str, Any]]) -> list[str]:
    actual = {
        (row["name"], int(row["version"])): row
        for row in snapshot(session)
        if row.get("version") is not None
    }
    errors: list[str] = []
    for row in expected:
        key = (row["name"], int(row["version"]))
        stored = actual.get(key)
        if not stored:
            errors.append(f"missing {key[0]} v{key[1]}")
        elif prompt_hash(stored) != prompt_hash(row):
            errors.append(f"hash mismatch {key[0]} v{key[1]}")
        elif stored.get("source") != "seed":
            errors.append(f"source mismatch {key[0]} v{key[1]}")
    return errors


def run(*, apply: bool, confirm: str, backup_path: Path | None = None) -> int:
    """Show a dry-run or perform a guarded force reseed."""
    seeds = [_seed_row(prompt) for prompt in SEED_PROMPTS]
    driver = _get_driver()
    try:
        with driver.session() as session:
            rows = snapshot(session)
            changes = _diff(rows, seeds)
            logger.info(
                "Target=%s rows=%d sources=%s changes=%d",
                _redacted_target(),
                len(rows),
                json.dumps(_source_counts(rows), sort_keys=True),
                len(changes),
            )
            logger.info("Diff=%s", json.dumps(changes, ensure_ascii=True))
            if not apply:
                if backup_path is not None:
                    backup = _write_backup(rows, backup_path)
                    logger.info("Read-only export=%s", backup)
                return 0
            if confirm != CONFIRM_TOKEN:
                raise ValueError(f"--confirm must equal {CONFIRM_TOKEN}")
            backup = _write_backup(rows, backup_path)
            logger.info("Backup=%s", backup)
            try:
                for prompt in SEED_PROMPTS:
                    _upsert_seed(session, prompt)
                errors = _verify(session, seeds)
                if errors:
                    raise RuntimeError("; ".join(errors))
            except Exception:
                logger.exception("Force reseed failed; restoring backup")
                restore(session, rows)
                raise
            logger.info("Verified %d seeded PromptConfig rows.", len(seeds))
            return 0
    finally:
        driver.close()


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply the force reseed")
    parser.add_argument("--confirm", default="", help="Required confirmation token")
    parser.add_argument("--backup", type=Path, help="Optional backup JSON path")
    args = parser.parse_args()
    return run(apply=args.apply, confirm=args.confirm, backup_path=args.backup)


if __name__ == "__main__":
    raise SystemExit(main())
