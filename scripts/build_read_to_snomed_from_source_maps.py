"""Build Read->SNOMED mapping from DMWB authoritative map tables.

Uses:
- DMWB NHS READ.mdb: RCT / CTV3 terms
- DMWB NHS Data Migration Maps.mdb: RCTSCTMAP / CTV3SCTMAP (source of truth)
- DMWB NHS SNOMED.mdb: SCT terms for SNOMED preferred term text
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pyodbc

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "external_content" / "trud-snomed-data-migration"
READ_DB = BASE / "DMWB NHS READ.mdb"
MAP_DB = BASE / "DMWB NHS Data Migration Maps.mdb"
SNOMED_DB = BASE / "DMWB NHS SNOMED.mdb"
OUT_PATH = BASE / "read_to_snomed.source_map.jsonl"
ODBC_DRIVER = "{Microsoft Access Driver (*.mdb, *.accdb)}"
TYP_PRIORITY = {1: 0, 2: 1, 0: 2, 3: 3}


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def decode_access_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-16le", errors="ignore").rstrip("\x00").strip()
    return str(value).strip()


def choose_read_term(t30: str, t60: str, t198: str) -> str:
    for candidate in (t60, t198, t30):
        if candidate.strip():
            return candidate.strip()
    return ""


def open_access_connection(path: Path) -> pyodbc.Connection:
    return pyodbc.connect(f"DRIVER={ODBC_DRIVER};DBQ={path.resolve()};")


def load_read_terms(conn: pyodbc.Connection) -> dict[str, dict[str, str]]:
    terms: dict[str, dict[str, str]] = {}
    cur = conn.cursor()
    for table in ("RCT", "CTV3"):
        for row in cur.execute(f"SELECT [CUI], [T30], [T60], [T198] FROM [{table}]"):
            read_code = decode_access_value(row[0])
            if not read_code:
                continue
            read_term = choose_read_term(
                decode_access_value(row[1]),
                decode_access_value(row[2]),
                decode_access_value(row[3]),
            )
            if not read_term:
                continue
            if read_code not in terms:
                terms[read_code] = {"read_term": read_term, "read_scheme": table}
    return terms


def load_snomed_pt(conn: pyodbc.Connection) -> dict[str, str]:
    best: dict[str, tuple[int, str]] = {}
    cur = conn.cursor()
    for row in cur.execute("SELECT [CUI], [TERM], [TYP], [STAT] FROM [SCT]"):
        code = decode_access_value(row[0])
        term = decode_access_value(row[1])
        if not code or not term:
            continue
        stat = int(row[3]) if row[3] is not None else 99
        if stat != 0:
            continue
        typ = int(row[2]) if row[2] is not None else 99
        prio = TYP_PRIORITY.get(typ, 99)
        current = best.get(code)
        if current is None or prio < current[0]:
            best[code] = (prio, term)
    return {k: v[1] for k, v in best.items()}


def load_source_maps(conn: pyodbc.Connection) -> dict[str, list[dict[str, Any]]]:
    mappings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    cur = conn.cursor()
    for table, scheme in (("RCTSCTMAP", "RCT"), ("CTV3SCTMAP", "CTV3")):
        for row in cur.execute(
            f"SELECT [SCUI], [STUI], [TCUI], [TTUI], [MAPTYP], [ASSURED] FROM [{table}]"
        ):
            read_code = decode_access_value(row[0])
            snomed_code = decode_access_value(row[2])
            if not read_code or not snomed_code:
                continue
            if not snomed_code.isdigit():
                continue
            mappings[read_code].append(
                {
                    "snomed_code": snomed_code,
                    "map_table": table,
                    "source_scheme": scheme,
                    "map_type": decode_access_value(row[4]),
                    "assured": bool(row[5]),
                    "source_term_id": decode_access_value(row[1]),
                    "target_term_id": decode_access_value(row[3]),
                }
            )
    return mappings


def pick_best_candidate(
    candidates: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    # deterministic sort: assured first, then map_type E first, then lowest code
    ranked = sorted(
        candidates,
        key=lambda x: (
            0 if x["assured"] else 1,
            0 if x["map_type"] == "E" else 1,
            x["snomed_code"],
        ),
    )
    unique_codes = []
    seen = set()
    for c in ranked:
        code = c["snomed_code"]
        if code in seen:
            continue
        seen.add(code)
        unique_codes.append(code)
    best = unique_codes[0] if unique_codes else ""
    return best, ranked


def build_rows(
    read_terms: dict[str, dict[str, str]],
    map_rows: dict[str, list[dict[str, Any]]],
    snomed_pt: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stats = Counter()
    for idx, read_code in enumerate(sorted(read_terms), start=1):
        read_meta = read_terms[read_code]
        candidates = map_rows.get(read_code, [])
        if not candidates:
            status = "unmapped_in_source_map"
            row = {
                "read_code": read_code,
                "read_term": read_meta["read_term"],
                "snomed_code": None,
                "snomed_term": "",
                "mapping_status": status,
                "mapping_source": "dmwb_source_maps",
                "candidate_count": 0,
                "candidates": [],
            }
            rows.append(row)
            stats[status] += 1
            continue

        best_code, ranked = pick_best_candidate(candidates)
        unique_codes = sorted({c["snomed_code"] for c in ranked})
        status = (
            "deterministic_source_map"
            if len(unique_codes) == 1
            else "ambiguous_source_map"
        )
        row = {
            "read_code": read_code,
            "read_term": read_meta["read_term"],
            "snomed_code": best_code if status == "deterministic_source_map" else None,
            "snomed_term": (
                snomed_pt.get(best_code, "")
                if status == "deterministic_source_map"
                else ""
            ),
            "mapping_status": status,
            "mapping_source": "dmwb_source_maps",
            "candidate_count": len(unique_codes),
            "candidates": [
                {
                    "snomed_code": code,
                    "snomed_term": snomed_pt.get(code, ""),
                    "assured_any": any(
                        c["assured"] for c in ranked if c["snomed_code"] == code
                    ),
                    "map_tables": sorted(
                        {c["map_table"] for c in ranked if c["snomed_code"] == code}
                    ),
                    "map_types": sorted(
                        {c["map_type"] for c in ranked if c["snomed_code"] == code}
                    ),
                }
                for code in unique_codes
            ],
        }
        rows.append(row)
        stats[status] += 1
        if idx % 50000 == 0:
            log(f"Build progress: {idx}/{len(read_terms)} rows")

    log(f"Status summary: {dict(stats)}")
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--read-db", type=Path, default=READ_DB)
    p.add_argument("--map-db", type=Path, default=MAP_DB)
    p.add_argument("--snomed-db", type=Path, default=SNOMED_DB)
    p.add_argument("--out", type=Path, default=OUT_PATH)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    log("Loading read terms")
    with open_access_connection(args.read_db) as c:
        read_terms = load_read_terms(c)
    log(f"Read terms loaded: {len(read_terms)}")

    log("Loading source maps")
    with open_access_connection(args.map_db) as c:
        map_rows = load_source_maps(c)
    log(f"Mapped read codes in source maps: {len(map_rows)}")

    log("Loading SNOMED preferred terms")
    with open_access_connection(args.snomed_db) as c:
        snomed_pt = load_snomed_pt(c)
    log(f"SNOMED preferred terms loaded: {len(snomed_pt)}")

    rows = build_rows(read_terms, map_rows, snomed_pt)
    write_jsonl(args.out, rows)
    log(f"Wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
