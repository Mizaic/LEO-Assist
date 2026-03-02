"""TRUD terminology sync: download, extract, and load into Neo4j.

Orchestrates:
  1. Fetch latest release metadata from the TRUD API.
  2. Download the archive (streaming, with progress events).
  3. Extract to external_content/.
  4. Run the terminology loader phases via asyncio.run().

Emitter is a Callable[[dict], None] that forwards events to an SSE queue.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

Emitter = Callable[[dict], None]

TRUD_BASE = "https://isd.digital.nhs.uk"

PACKAGES: dict[str, dict] = {
    "snomed": {
        "item_id": 101,
        "label": "SNOMED CT UK Clinical Edition",
        "dest": "trud-snomed-uk-clinical-edition",
        "phases": {1, 2, 3},
    },
    "dmd": {
        "item_id": 24,
        "label": "dm+d (Medicines and Devices)",
        "dest": "trud-snomed-ct-drug-extension",
        "phases": {5},
    },
}


def _api_key() -> str:
    return os.environ.get("NHS_TRUD_API_KEY", "")


def get_trud_release(item_id: int) -> dict | None:
    """Fetch the latest release metadata from the TRUD API."""
    key = _api_key()
    url = f"{TRUD_BASE}/trud/api/v1/keys/{key}/items/{item_id}/releases?latest"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read())
        return (data.get("releases") or [None])[0]
    except Exception as exc:
        logger.warning("TRUD API error item %s: %s", item_id, exc)
        return None


def _neo4j_credentials() -> tuple[str, str, str]:
    return (
        os.environ.get("KNOWLEDGE_GRAPH_NEO4J_URI", ""),
        os.environ.get("KNOWLEDGE_GRAPH_NEO4J_USERNAME", ""),
        os.environ.get("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", ""),
    )


def get_neo4j_counts() -> dict:
    """Query active node and relationship counts from the knowledge graph."""
    from neo4j import GraphDatabase

    uri, user, password = _neo4j_credentials()
    if not all([uri, user, password]):
        return {}

    queries = {
        "active_concepts": "MATCH (c:Concept {active:true}) RETURN count(c) AS n",
        "terms": "MATCH (t:Term) RETURN count(t) AS n",
        "is_a_rels": "MATCH ()-[:IS_A]->() RETURN count(*) AS n",
        "icd10_maps": "MATCH ()-[:MAPS_TO_ICD10]->() RETURN count(*) AS n",
        "read_maps": "MATCH ()-[:MAPS_TO_READ]->() RETURN count(*) AS n",
    }
    driver = GraphDatabase.driver(uri, auth=(user, password))
    counts: dict = {}
    try:
        with driver.session() as session:
            for key, q in queries.items():
                counts[key] = session.run(q).single()["n"]
    except Exception as exc:
        logger.warning("Neo4j count error: %s", exc)
    finally:
        driver.close()
    return counts


def _local_dirs(dest_dir: str, external: Path) -> list[str]:
    """Return sorted dated directory names found under dest_dir."""
    pkg_dir = external / dest_dir
    if not pkg_dir.exists():
        return []
    return sorted(d.name for d in pkg_dir.iterdir() if d.is_dir())


def get_status(external: Path) -> dict:
    """Return TRUD release info and Neo4j counts for the status card."""
    packages = {}
    for key, meta in PACKAGES.items():
        release = get_trud_release(meta["item_id"])
        local_dirs = _local_dirs(meta["dest"], external)
        local_ver = local_dirs[-1] if local_dirs else None
        trud_date = release.get("releaseDate", "") if release else ""
        up_to_date = bool(local_ver and trud_date and trud_date.replace("-", "") in local_ver)
        packages[key] = {
            "label": meta["label"],
            "local_version": local_ver,
            "trud_version": release.get("name") if release else None,
            "trud_date": trud_date or None,
            "trud_size_mb": (
                round(release.get("archiveFileSizeBytes", 0) / 1024 / 1024)
                if release
                else None
            ),
            "up_to_date": up_to_date,
        }
    return {"packages": packages, "neo4j": get_neo4j_counts()}


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------


def _download_file(url: str, dest: Path, emit: Emitter) -> None:
    """Stream-download url to dest, emitting progress events every 5%."""
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        last_pct = -1
        with open(dest, "wb") as fh:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = int(downloaded * 100 / total)
                    if pct >= last_pct + 5:
                        emit({
                            "type": "download_progress",
                            "pct": pct,
                            "mb": round(downloaded / 1024 / 1024),
                        })
                        last_pct = pct


def _extract_snomed(zip_path: Path, dest_dir: Path, emit: Emitter) -> None:
    """Extract SNOMED zip, adding new dated directories alongside existing ones."""
    emit({"type": "log", "msg": f"Extracting {zip_path.name} to {dest_dir.name}/"})
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    emit({"type": "log", "msg": "Extraction complete."})


def _extract_dmd(zip_path: Path, dest_dir: Path, emit: Emitter) -> None:
    """Extract dm+d zip, stripping the top-level wrapper directory."""
    emit({"type": "log", "msg": f"Extracting {zip_path.name} to {dest_dir.name}/"})
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        prefixes = {n.split("/")[0] for n in names if "/" in n}
        strip = prefixes.pop() if len(prefixes) == 1 else None
        for member in zf.infolist():
            target = member.filename
            if strip and target.startswith(strip + "/"):
                target = target[len(strip) + 1:]
            if not target:
                continue
            out = dest_dir / target
            if member.is_dir():
                out.mkdir(parents=True, exist_ok=True)
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(out, "wb") as dst:
                    dst.write(src.read())
    emit({"type": "log", "msg": "Extraction complete."})


# ---------------------------------------------------------------------------
# Loader integration
# ---------------------------------------------------------------------------


class _LogCapture(logging.Handler):
    """Forwards loader log records to the SSE emit function."""

    def __init__(self, emit: Emitter) -> None:
        super().__init__()
        self._emit = emit

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._emit({
                "type": "log",
                "msg": self.format(record),
                "level": record.levelname.lower(),
            })
        except Exception:
            pass


def _run_loader(external: Path, phases: set[int], emit: Emitter) -> None:
    """Run the terminology loader with log capture, in a fresh asyncio loop."""
    from services.terminology.scripts.loaders.run_all import main as loader_main

    handler = _LogCapture(emit)
    handler.setFormatter(logging.Formatter("%(name)s - %(message)s"))
    root_logger = logging.getLogger("services.terminology.scripts.loaders")
    root_logger.addHandler(handler)
    try:
        asyncio.run(loader_main(external, phases))
    finally:
        root_logger.removeHandler(handler)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _sync_one_package(key: str, external: Path, emit: Emitter) -> bool:
    """Download and extract one TRUD package. Returns True on success."""
    meta = PACKAGES[key]
    release = get_trud_release(meta["item_id"])
    if not release:
        emit({"type": "sync_error", "msg": f"Could not reach TRUD API for {meta['label']}."})
        return False

    url = release.get("archiveFileUrl", "")
    size_mb = round(release.get("archiveFileSizeBytes", 0) / 1024 / 1024)
    emit({
        "type": "download_start",
        "package": key,
        "label": meta["label"],
        "version": release.get("name", ""),
        "size_mb": size_mb,
    })

    dest_dir = external / meta["dest"]
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        _download_file(url, tmp_path, emit)
        emit({"type": "download_done", "package": key})
        if key == "dmd":
            _extract_dmd(tmp_path, dest_dir, emit)
        else:
            _extract_snomed(tmp_path, dest_dir, emit)
    finally:
        tmp_path.unlink(missing_ok=True)

    return True


def full_sync(
    external: Path,
    packages: list[str],
    phases: set[int],
    emit: Emitter,
) -> None:
    """Orchestrate download, extract, and load for the requested packages."""
    t0 = time.monotonic()
    emit({"type": "log", "msg": f"Starting sync for: {', '.join(packages)}"})

    for key in packages:
        if key not in PACKAGES:
            emit({"type": "log", "msg": f"Unknown package '{key}' - skipped.", "level": "warning"})
            continue
        ok = _sync_one_package(key, external, emit)
        if not ok:
            emit({"type": "sync_error", "msg": f"Download failed for {key}. Aborting."})
            return

    if not phases:
        emit({"type": "log", "msg": "No loader phases requested. Skipping load step."})
    else:
        emit({"type": "phase_start", "phases": sorted(phases)})
        try:
            _run_loader(external, phases, emit)
        except Exception as exc:
            emit({"type": "sync_error", "msg": f"Loader failed: {exc}"})
            return

    elapsed = round(time.monotonic() - t0)
    emit({"type": "sync_done", "duration_s": elapsed})
