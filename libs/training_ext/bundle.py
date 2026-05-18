"""Model artifact bundle assembly.

Atlas trace:
  DO: DO-54397CCD
  DI: DI-3FDBB57B

The bundle is the folder tar-ed up and uploaded to blob storage. Beyond the
spaCy model itself, we include:

* ``calibration.json`` — per-label thresholds (Wave 3)
* ``orth_variants.json`` — the augmenter table used during training (Wave 2)
* ``span_alignment_report.json`` — spans whose char offsets moved (Wave 2)
* ``bundle_manifest.json`` — SHA256 of every file in the bundle plus metadata
  (training timestamp, dataset hashes, model version) so the inference service
  can verify integrity and the registry can prove provenance.

The manifest is the source of truth for "what shipped together". The
inference service refuses to honour a calibration file whose SHA does not
match the manifest, so an out-of-band swap of calibration.json cannot
silently change production behaviour.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

_MANIFEST_NAME = "bundle_manifest.json"
_BUNDLED_FILES: tuple[str, ...] = (
    "calibration.json",
    "orth_variants.json",
    "span_alignment_report.json",
    "export_meta.json",
)


@dataclass
class BundleManifest:
    model_version: str
    built_at: str
    dataset_hash: str
    file_hashes: dict[str, str] = field(default_factory=dict)
    extras: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "model_version": self.model_version,
            "built_at": self.built_at,
            "dataset_hash": self.dataset_hash,
            "file_hashes": dict(self.file_hashes),
            "extras": dict(self.extras),
        }


def assemble_bundle(
    model_dir: Path,
    *,
    version: str,
    source_dir: Path | None = None,
    dataset_hash: str = "",
    extras: dict[str, str] | None = None,
    extra_files: Iterable[Path] = (),
) -> BundleManifest:
    """Copy Wave-2/Wave-3 artifacts into ``model_dir`` and write the manifest.

    Args:
        model_dir: The spaCy model directory that will be tar-ed and uploaded.
        version: Logical model version (``20260424-153000``).
        source_dir: Directory where ``calibration.json`` / ``orth_variants.json``
            etc. live. Defaults to ``model_dir`` when omitted.
        dataset_hash: Hash of the training dataset (train_split_hash).
        extras: Arbitrary provenance pairs (e.g. git SHA, base model).
        extra_files: Paths of additional files to include in the bundle
            (copied into ``model_dir`` if not already present).

    Returns:
        The assembled :class:`BundleManifest`.
    """
    model_dir.mkdir(parents=True, exist_ok=True)
    source = source_dir or model_dir
    extras = dict(extras or {})

    for name in _BUNDLED_FILES:
        src = source / name
        dst = model_dir / name
        if src.exists() and src != dst:
            try:
                shutil.copyfile(src, dst)
            except OSError as exc:
                logger.warning("[bundle] could not copy %s: %s", src, exc)

    for extra in extra_files:
        if extra.exists():
            dst = model_dir / extra.name
            if extra.resolve() != dst.resolve():
                shutil.copyfile(extra, dst)

    file_hashes: dict[str, str] = {}
    for path in sorted(model_dir.rglob("*")):
        if path.is_file() and path.name != _MANIFEST_NAME:
            rel = path.relative_to(model_dir).as_posix()
            file_hashes[rel] = _sha256(path)

    manifest = BundleManifest(
        model_version=version,
        built_at=datetime.datetime.utcnow().isoformat() + "Z",
        dataset_hash=dataset_hash,
        file_hashes=file_hashes,
        extras=extras,
    )
    (model_dir / _MANIFEST_NAME).write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    logger.info(
        "[bundle] Wrote %s with %d files (version=%s)",
        _MANIFEST_NAME,
        len(file_hashes),
        version,
    )
    return manifest


def verify_bundle(model_dir: Path) -> list[str]:
    """Compare actual file hashes against the manifest.

    Returns a list of human-readable discrepancies (empty when the bundle is
    intact). The inference service refuses to honour calibration.json / other
    sidecars when this returns non-empty.
    """
    manifest_path = model_dir / _MANIFEST_NAME
    if not manifest_path.exists():
        return ["bundle_manifest.json missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"bundle_manifest.json unreadable: {exc}"]
    recorded: dict[str, str] = manifest.get("file_hashes") or {}
    discrepancies: list[str] = []
    for rel, expected in recorded.items():
        path = model_dir / rel
        if not path.exists():
            discrepancies.append(f"missing file: {rel}")
            continue
        actual = _sha256(path)
        if actual != expected:
            discrepancies.append(
                f"hash mismatch for {rel} (expected {expected[:12]}…, "
                f"got {actual[:12]}…)"
            )
    return discrepancies


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()
