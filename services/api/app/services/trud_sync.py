"""TRUD terminology sync: download, extract, and load into Neo4j.

Atlas trace:
  DO: DO-95090147
  DI: DI-B8C57B22 (load), DI-698EE6EE (fail-safe), DI-81022210 (staleness), DI-2AD4CCC3 (audit log)
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-95090147")

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
import re
import shutil
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
    "icd10": {
        "item_id": 259,
        "label": "NHS ICD-10 5th Edition (XML)",
        "dest": "trud-nhs-icd10",
        "phases": {6},
    },
    "opcs4": {
        "item_id": 119,
        "label": "OPCS-4 (Procedural classification)",
        "dest": "trud-nhs-opcs4",
        "phases": {7},
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
        "icd10_codes": "MATCH (c:Icd10Code) RETURN count(c) AS n",
        "opcs4_codes": "MATCH (c:OpcsCode) RETURN count(c) AS n",
        "opcs4_maps": "MATCH ()-[:MAPS_TO_OPCS4]->() RETURN count(*) AS n",
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


def _snomed_local_date(external: Path) -> str | None:
    """Return the most recent 8-digit date found across all SNOMED dated dirs.

    e.g. SnomedCT_UKClinicalRF2_PRODUCTION_20260211T000001Z -> '20260211'
    Returns as 'YYYY-MM-DD' or None if no dated directories exist.
    """
    pkg_dir = external / PACKAGES["snomed"]["dest"]
    if not pkg_dir.exists():
        return None
    dates = []
    for d in pkg_dir.iterdir():
        if not d.is_dir():
            continue
        m = re.search(r"(\d{8})", d.name)
        if m:
            dates.append(m.group(1))
    if not dates:
        return None
    raw = max(dates)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"


def _dmd_local_date(external: Path) -> str | None:
    """Return the date embedded in dm+d XML filenames as 'YYYY-MM-DD'.

    NHS BSA filenames use format: f_vtm2_<ver>DDMMYY.xml
    e.g. f_vtm2_3190226.xml -> last 6 digits = 190226 -> 2026-02-19
    """
    pkg_dir = external / PACKAGES["dmd"]["dest"]
    if not pkg_dir.exists():
        return None
    for f in sorted(pkg_dir.glob("f_vtm2_*.xml"), reverse=True):
        m = re.search(r"_(\d+)\.xml$", f.name)
        if m:
            digits = m.group(1)[-6:]  # last 6 digits = DDMMYY
            if len(digits) == 6:
                return f"20{digits[4:]}-{digits[2:4]}-{digits[:2]}"
    return None


def _trud_release_date_in_name(release_name: str) -> str | None:
    """Extract an 8-digit date from a TRUD release name.

    e.g. 'SNOMEDCT2_41.5.0_20260211000001' -> '20260211'
    Returns 'YYYY-MM-DD' or None.
    """
    m = re.search(r"(\d{8})", release_name or "")
    if not m:
        return None
    raw = m.group(1)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"


def _snomed_up_to_date(local_date: str | None, release: dict | None) -> bool:
    """True when the local SNOMED date matches the date embedded in the TRUD release name."""
    if not local_date or not release:
        return False
    trud_name_date = _trud_release_date_in_name(release.get("name", ""))
    return bool(trud_name_date and local_date == trud_name_date)


def _dmd_up_to_date(local_date: str | None, release: dict | None) -> bool:
    """True when the local dm+d date is >= the TRUD release date."""
    if not local_date or not release:
        return False
    trud_date = release.get("releaseDate", "")
    return bool(trud_date and local_date >= trud_date)


def _generic_local_date(external: Path, key: str) -> str | None:
    """Most recent file mtime under a package's extracted directory.

    Used for ICD-10 / OPCS-4 where the release does not stamp a date into
    the filename or directory name.
    """
    pkg_dir = external / PACKAGES[key]["dest"]
    if not pkg_dir.exists():
        return None
    latest_mtime = 0.0
    for f in pkg_dir.rglob("*"):
        if not f.is_file():
            continue
        latest_mtime = max(latest_mtime, f.stat().st_mtime)
    if not latest_mtime:
        return None
    return time.strftime("%Y-%m-%d", time.gmtime(latest_mtime))


def _generic_up_to_date(local_date: str | None, release: dict | None) -> bool:
    """True when the local mtime is on or after the TRUD release date."""
    if not local_date or not release:
        return False
    trud_date = release.get("releaseDate", "")
    return bool(trud_date and local_date >= trud_date)


def _package_status(key: str, external: Path, release: dict | None) -> dict:
    """Build the status dict for one package."""
    if key == "snomed":
        local_date = _snomed_local_date(external)
        up_to_date = _snomed_up_to_date(local_date, release)
    elif key == "dmd":
        local_date = _dmd_local_date(external)
        up_to_date = _dmd_up_to_date(local_date, release)
    else:
        local_date = _generic_local_date(external, key)
        up_to_date = _generic_up_to_date(local_date, release)

    return {
        "label": PACKAGES[key]["label"],
        "local_version": local_date,
        "trud_version": release.get("name") if release else None,
        "trud_date": release.get("releaseDate") if release else None,
        "trud_size_mb": (
            round(release.get("archiveFileSizeBytes", 0) / 1024 / 1024)
            if release
            else None
        ),
        "up_to_date": up_to_date,
    }


def get_status(external: Path) -> dict:
    """Return TRUD release info and Neo4j counts for the status page."""
    packages = {
        key: _package_status(key, external, get_trud_release(meta["item_id"]))
        for key, meta in PACKAGES.items()
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
                        emit(
                            {
                                "type": "download_progress",
                                "pct": pct,
                                "mb": round(downloaded / 1024 / 1024),
                            }
                        )
                        last_pct = pct


def _safe_zip_target(dest_dir: Path, member_name: str) -> Path | None:
    """Resolve the on-disk target for a zip member, rejecting path traversal.

    Returns the resolved Path if it is contained within dest_dir, else None.
    Defends against archives that contain absolute paths, '..' segments, or
    Windows-style drive letters (Zip-Slip / CVE-2018-1002201 family).
    """
    if not member_name or member_name.startswith(("/", "\\")):
        return None
    if ":" in member_name and len(member_name) > 1 and member_name[1] == ":":
        return None
    candidate = (dest_dir / member_name).resolve()
    base = dest_dir.resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def _extract_snomed(zip_path: Path, dest_dir: Path, emit: Emitter) -> None:
    """Extract SNOMED zip, adding new dated directories alongside existing ones.

    Each member is path-normalised and verified to land inside dest_dir before
    being written, so a hostile or corrupted archive cannot escape the
    extraction root.
    """
    emit({"type": "log", "msg": f"Extracting {zip_path.name} to {dest_dir.name}/"})
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            target = _safe_zip_target(dest_dir, member.filename)
            if target is None:
                logger.warning(
                    "trud_sync: refusing to extract unsafe path %r from %s",
                    member.filename,
                    zip_path.name,
                )
                continue
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    emit({"type": "log", "msg": "Extraction complete."})


def _extract_dmd(zip_path: Path, dest_dir: Path, emit: Emitter) -> None:
    """Extract dm+d zip, stripping the top-level wrapper directory.

    Like _extract_snomed, every resolved target is checked against dest_dir
    so traversal payloads ('../etc/passwd', absolute paths) cannot escape.
    """
    emit({"type": "log", "msg": f"Extracting {zip_path.name} to {dest_dir.name}/"})
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        prefixes = {n.split("/")[0] for n in names if "/" in n}
        strip = prefixes.pop() if len(prefixes) == 1 else None
        for member in zf.infolist():
            target_name = member.filename
            if strip and target_name.startswith(strip + "/"):
                target_name = target_name[len(strip) + 1 :]
            if not target_name:
                continue
            out = _safe_zip_target(dest_dir, target_name)
            if out is None:
                logger.warning(
                    "trud_sync: refusing to extract unsafe path %r from %s",
                    member.filename,
                    zip_path.name,
                )
                continue
            if member.is_dir():
                out.mkdir(parents=True, exist_ok=True)
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
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
            self._emit(
                {
                    "type": "log",
                    "msg": self.format(record),
                    "level": record.levelname.lower(),
                }
            )
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
        emit(
            {
                "type": "sync_error",
                "msg": f"Could not reach TRUD API for {meta['label']}.",
            }
        )
        return False

    url = release.get("archiveFileUrl", "")
    size_mb = round(release.get("archiveFileSizeBytes", 0) / 1024 / 1024)
    emit(
        {
            "type": "download_start",
            "package": key,
            "label": meta["label"],
            "version": release.get("name", ""),
            "size_mb": size_mb,
        }
    )

    dest_dir = external / meta["dest"]
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        _download_file(url, tmp_path, emit)
        emit({"type": "download_done", "package": key})
        if key == "snomed":
            _extract_snomed(tmp_path, dest_dir, emit)
        else:
            _extract_dmd(tmp_path, dest_dir, emit)
    except Exception as exc:
        emit({"type": "sync_error", "msg": f"Download/extract failed for {meta['label']}: {exc}"})
        return False
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
            emit(
                {
                    "type": "log",
                    "msg": f"Unknown package '{key}' - skipped.",
                    "level": "warning",
                }
            )
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
