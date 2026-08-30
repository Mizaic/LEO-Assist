"""Disk bundle helpers for local referral-chunk validation.

Atlas trace:
  DO: DO-58BD2EA0
  DI: DI-ACA9659D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-58BD2EA0")

The pull script writes one folder per referral. The seed script
reads that folder and upserts chunks into a local Neo4j. Production
is never written from these helpers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from libs.deid import deidentify


@dataclass(frozen=True)
class ValidationBundle:
    """On-disk pull output for one referral."""

    path: Path
    manifest: dict[str, Any]
    chunks: list[dict[str, Any]]
    chunks_deid: list[dict[str, Any]]


def deidentify_chunk_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return copies of chunk records with PHI patterns redacted."""
    out: list[dict[str, Any]] = []
    for record in records:
        copy = dict(record)
        copy["text"] = deidentify(str(record.get("text") or "")).text
        out.append(copy)
    return out


def write_bundle(
    output_dir: Path,
    *,
    referral_id: str,
    manifest: dict[str, Any],
    chunks: list[dict[str, Any]],
    chunks_deid: list[dict[str, Any]] | None = None,
) -> Path:
    """Write manifest and chunk JSON under ``output_dir/<referral_id>``."""
    dest = output_dir / str(referral_id)
    dest.mkdir(parents=True, exist_ok=True)
    payload = dict(manifest)
    payload.setdefault("referral_id", referral_id)
    payload.setdefault("chunk_count", len(chunks))
    payload.setdefault("written_at", datetime.now(timezone.utc).isoformat())
    _write_json(dest / "manifest.json", payload)
    _write_json(dest / "chunks.json", chunks)
    if chunks_deid is not None:
        _write_json(dest / "chunks_deid.json", chunks_deid)
    return dest


def load_bundle(input_dir: Path) -> ValidationBundle:
    """Load a previously written validation bundle."""
    dest = Path(input_dir)
    manifest_path = dest / "manifest.json"
    chunks_path = dest / "chunks.json"
    if not manifest_path.is_file() or not chunks_path.is_file():
        raise FileNotFoundError(f"bundle is missing manifest or chunks: {dest}")
    deid_path = dest / "chunks_deid.json"
    chunks_deid: list[dict[str, Any]] = []
    if deid_path.is_file():
        chunks_deid = _read_json(deid_path)
    return ValidationBundle(
        path=dest,
        manifest=_read_json(manifest_path),
        chunks=_read_json(chunks_path),
        chunks_deid=chunks_deid,
    )


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
