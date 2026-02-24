"""Build deterministic Read->SNOMED crosswalk from DMWB MDB tables.

This script joins multiple Read-side tables (RCT, CTV3, RCTEQV, CTV3EQV, ctv3_rmf)
to create Read equivalence groups, then links groups to SNOMED concepts via exact
normalized term matching against SCT terms. It emits a traceable JSONL output with
deterministic provenance.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pyodbc


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "external_content" / "trud-snomed-data-migration"
READ_DB = BASE / "DMWB NHS READ.mdb"
SNOMED_DB = BASE / "DMWB NHS SNOMED.mdb"
OUT_PATH = BASE / "read_to_snomed.crosswalk.jsonl"
ODBC_DRIVER = "{Microsoft Access Driver (*.mdb, *.accdb)}"
READ_CODE_RE = re.compile(r"^[A-Za-z0-9.]{3,8}$")
PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
SPACE_RE = re.compile(r"\s+")
TYP_PRIORITY = {1: 0, 2: 1, 0: 2, 3: 3}


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def decode_access_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-16le", errors="ignore").rstrip("\x00").strip()
    return str(value).strip()


def normalize_term(text: str) -> str:
    text = text.lower().strip()
    text = PUNCT_RE.sub(" ", text)
    text = SPACE_RE.sub(" ", text)
    return text.strip()


def choose_read_term(t30: str, t60: str, t198: str) -> str:
    for candidate in (t60, t198, t30):
        if candidate.strip():
            return candidate.strip()
    return ""


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.rank: dict[str, int] = {}

    def add(self, x: str) -> None:
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0

    def find(self, x: str) -> str:
        self.add(x)
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def open_access_connection(path: Path) -> pyodbc.Connection:
    return pyodbc.connect(f"DRIVER={ODBC_DRIVER};DBQ={path.resolve()};")


def load_read_terms(conn: pyodbc.Connection) -> tuple[dict[str, str], dict[str, set[str]]]:
    read_term: dict[str, str] = {}
    read_sources: dict[str, set[str]] = defaultdict(set)
    cursor = conn.cursor()
    for table in ("RCT", "CTV3"):
        for row in cursor.execute(f"SELECT [CUI], [T30], [T60], [T198] FROM [{table}]"):
            code = decode_access_value(row[0])
            if not READ_CODE_RE.match(code):
                continue
            term = choose_read_term(
                decode_access_value(row[1]),
                decode_access_value(row[2]),
                decode_access_value(row[3]),
            )
            if not term:
                continue
            if code not in read_term:
                read_term[code] = term
            read_sources[code].add(table)
    return read_term, read_sources


def add_edges_from_eqv(uf: UnionFind, conn: pyodbc.Connection) -> int:
    edges = 0
    cursor = conn.cursor()
    for table in ("RCTEQV", "CTV3EQV"):
        for row in cursor.execute(f"SELECT [CUI1], [CUI2] FROM [{table}]"):
            a = decode_access_value(row[0])
            b = decode_access_value(row[1])
            if not READ_CODE_RE.match(a) or not READ_CODE_RE.match(b):
                continue
            uf.union(a, b)
            edges += 1
    return edges


def add_edges_from_rmf(uf: UnionFind, conn: pyodbc.Connection) -> int:
    edges = 0
    cursor = conn.cursor()
    for row in cursor.execute("SELECT [NEWCUI], [OLDCUI] FROM [ctv3_rmf]"):
        new_code = decode_access_value(row[0])
        old_code = decode_access_value(row[1])
        if not READ_CODE_RE.match(new_code) or not READ_CODE_RE.match(old_code):
            continue
        uf.union(new_code, old_code)
        edges += 1
    return edges


def build_snomed_maps(
    conn: pyodbc.Connection,
) -> tuple[dict[str, str], dict[str, set[str]], dict[str, str]]:
    code_to_pt: dict[str, tuple[int, str]] = {}
    term_to_codes: dict[str, set[str]] = defaultdict(set)
    code_to_fsn: dict[str, str] = {}
    cursor = conn.cursor()
    for row in cursor.execute("SELECT [CUI], [TERM], [TYP], [STAT] FROM [SCT]"):
        code = decode_access_value(row[0])
        term = decode_access_value(row[1])
        if not code or not term:
            continue
        typ = int(row[2]) if row[2] is not None else 99
        stat = int(row[3]) if row[3] is not None else 99
        if stat != 0:
            continue

        nterm = normalize_term(term)
        if nterm:
            term_to_codes[nterm].add(code)

        if typ == 3 and code not in code_to_fsn:
            code_to_fsn[code] = term
        prio = TYP_PRIORITY.get(typ, 99)
        existing = code_to_pt.get(code)
        if existing is None or prio < existing[0]:
            code_to_pt[code] = (prio, term)

    pt_map = {k: v[1] for k, v in code_to_pt.items()}
    return pt_map, term_to_codes, code_to_fsn


def group_read_codes(uf: UnionFind, read_codes: set[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for code in read_codes:
        groups[uf.find(code)].append(code)
    for root in groups:
        groups[root].sort()
    return groups


def choose_group_term(codes: list[str], read_term: dict[str, str]) -> str:
    for code in codes:
        if code in read_term:
            return read_term[code]
    return ""


def build_crosswalk_rows(
    groups: dict[str, list[str]],
    read_term: dict[str, str],
    read_sources: dict[str, set[str]],
    term_to_codes: dict[str, set[str]],
    pt_map: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    processed = 0
    total = len(groups)
    for root, codes in groups.items():
        group_term = choose_group_term(codes, read_term)
        normalized = normalize_term(group_term)
        candidates = sorted(term_to_codes.get(normalized, set())) if normalized else []

        status = "unmapped"
        chosen_code: str | None = None
        if len(candidates) == 1:
            status = "deterministic_exact_term"
            chosen_code = candidates[0]
        elif len(candidates) > 1:
            status = "ambiguous_exact_term"

        mapped_pt = pt_map.get(chosen_code, "") if chosen_code else ""
        trace = {
            "group_root": root,
            "group_size": len(codes),
            "read_codes": codes,
            "sources": sorted({src for c in codes for src in read_sources.get(c, set())}),
            "normalized_term": normalized,
            "candidate_count": len(candidates),
        }
        candidate_detail = [
            {"concept_id": c, "term": pt_map.get(c, "")}
            for c in candidates
        ]

        for code in codes:
            rows.append(
                {
                    "read_code": code,
                    "read_term": read_term.get(code, group_term),
                    "mapping_status": status,
                    "snomed_code": chosen_code,
                    "snomed_term": mapped_pt if chosen_code else "",
                    "candidate_snomed_codes": candidates,
                    "candidate_snomed_terms": candidate_detail,
                    "mapping_source": "dmwb_multi_table_join",
                    "trace": trace,
                }
            )
        processed += 1
        if processed % 10000 == 0:
            log(f"Crosswalk progress: groups={processed}/{total} rows={len(rows)}")
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for row in rows:
        out[row["mapping_status"]] += 1
    return dict(out)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-db", type=Path, default=READ_DB)
    parser.add_argument("--snomed-db", type=Path, default=SNOMED_DB)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log("Building deterministic Read->SNOMED crosswalk")
    uf = UnionFind()

    with open_access_connection(args.read_db) as read_conn:
        read_term, read_sources = load_read_terms(read_conn)
        for code in read_term:
            uf.add(code)
        eqv_edges = add_edges_from_eqv(uf, read_conn)
        rmf_edges = add_edges_from_rmf(uf, read_conn)

    log(
        f"Loaded read terms={len(read_term)} eqv_edges={eqv_edges} rmf_edges={rmf_edges}"
    )

    with open_access_connection(args.snomed_db) as snomed_conn:
        pt_map, term_to_codes, _ = build_snomed_maps(snomed_conn)
    log(
        f"Loaded snomed_pt={len(pt_map)} normalized_terms={len(term_to_codes)}"
    )

    groups = group_read_codes(uf, set(read_term.keys()))
    log(f"Built equivalence groups={len(groups)}")
    rows = build_crosswalk_rows(groups, read_term, read_sources, term_to_codes, pt_map)
    write_jsonl(args.out, rows)

    stats = summarize(rows)
    log(f"Wrote rows={len(rows)} to {args.out}")
    log(f"Status summary: {stats}")


if __name__ == "__main__":
    main()
