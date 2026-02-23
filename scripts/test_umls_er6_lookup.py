#!/usr/bin/env python3
"""
Test script for UMLS ER6 lookup pattern.

Implements the NLM query pattern for term-to-code lookup:
https://www.nlm.nih.gov/research/umls/implementation_resources/query_diagrams/er6.html

Pattern:
  1. Word search: MRXW_ENG.RRF (wd) -> (CUI, LUI, SUI)
  2. Atom lookup: MRCONSO.RRF (CUI) -> preferred term
  3. UMLS API: CUI -> SNOMED CT and ICD-10 codes (when --api)

Output: UMLS CUI, preferred term, and codes for SNOMED, ICD-10.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterator

# Allow importing umls_cui_to_codes from same directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

# RRF column indices (0-based) from MRFILES.RRF
MRXW_ENG_COLS = ("LAT", "WD", "CUI", "LUI", "SUI")  # 5 cols
MRCONSO_COLS = (
    "CUI", "LAT", "TS", "LUI", "STT", "SUI", "ISPREF", "AUI", "SAUI",
    "SCUI", "SDUI", "SAB", "TTY", "CODE", "STR", "SRL", "SUPPRESS", "CVF",
)  # 18 cols

# SNOMED and ICD-10 source abbreviations (root SABs; UMLS uses versionless in data)
SNOMED_SABS = frozenset({
    "SNOMEDCT_US", "SNOMEDCT_UK", "SNOMEDCT", "SCTSPA",
})
ICD10_SABS = frozenset({
    "ICD10", "ICD10CM", "ICD10PCS", "ICD10AM", "ICD10AE", "ICD10DUT",
})


def parse_rrf_line(line: str) -> list[str]:
    """Parse RRF line: pipe-delimited, trailing pipe yields empty last element."""
    return [f.strip() for f in line.rstrip("\r\n").split("|") if True]


def stream_mrxw_by_word(
    path: Path,
    word: str,
    lang: str = "ENG",
) -> Iterator[tuple[str, str, str]]:
    """
    Stream MRXW_ENG.RRF for rows matching word (regular word index).
    Yields (CUI, LUI, SUI) per match.
    """
    word_lower = word.lower()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = parse_rrf_line(line)
            if len(parts) < 5:
                continue
            lat, wd, cui, lui, sui = parts[0], parts[1], parts[2], parts[3], parts[4]
            if lat == lang and wd == word_lower:
                yield (cui, lui, sui)


def stream_mrxnw_by_word(
    path: Path,
    word: str,
    lang: str = "ENG",
) -> Iterator[tuple[str, str, str]]:
    """
    Stream MRXNW_ENG.RRF for rows matching normalized word.
    Yields (CUI, LUI, SUI) per match.
    """
    word_lower = word.lower()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = parse_rrf_line(line)
            if len(parts) < 5:
                continue
            lat, nwd, cui, lui, sui = parts[0], parts[1], parts[2], parts[3], parts[4]
            if lat == lang and nwd == word_lower:
                yield (cui, lui, sui)


def stream_mrconso_by_cui(
    path: Path,
    cui_set: set[str],
) -> Iterator[dict]:
    """
    Stream MRCONSO.RRF for rows where CUI in set.
    Yields ALL atoms for each concept (needed for SNOMED/ICD10 from other term forms).
    """
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = parse_rrf_line(line)
            if len(parts) < 15:
                continue
            cui = parts[0]
            if cui not in cui_set:
                continue
            yield {
                "cui": cui,
                "sui": parts[5],
                "str": parts[14] if len(parts) > 14 else "",
                "sab": parts[11] if len(parts) > 11 else "",
                "tty": parts[12] if len(parts) > 12 else "",
                "code": parts[13] if len(parts) > 13 else "",
                "ispref": parts[6] if len(parts) > 6 else "",
            }


def run_lookup(
    meta_dir: Path,
    word: str,
    max_cui: int = 50,
    use_normalized: bool = False,
    show_all_sabs: bool = False,
    use_api: bool = True,
) -> None:
    """Execute ER6 lookup and print results."""
    index_name = "MRXNW_ENG.RRF" if use_normalized else "MRXW_ENG.RRF"
    index_path = meta_dir / index_name
    mrconso_path = meta_dir / "MRCONSO.RRF"

    if not index_path.exists():
        print(f"ERROR: {index_path} not found")
        return
    if not mrconso_path.exists():
        print(f"ERROR: {mrconso_path} not found")
        return

    # Step 1: Collect CUIs from word index (ER6 pattern)
    stream_fn = stream_mrxnw_by_word if use_normalized else stream_mrxw_by_word
    cui_set: set[str] = set()
    for cui, _lui, _sui in stream_fn(index_path, word):
        cui_set.add(cui)
        if len(cui_set) >= max_cui:
            break

    if not cui_set:
        print(f"No matches for word '{word}' in {index_name}")
        return

    idx_type = "normalized word (NWD)" if use_normalized else "regular word (WD)"
    print(f"Found {len(cui_set)} concepts for '{word}' [{idx_type}]")
    print("-" * 80)

    # Step 2: Fetch ALL atoms for each CUI (needed for SNOMED/ICD10 from any term form)
    atoms_by_cui: dict[str, list[dict]] = {}
    for atom in stream_mrconso_by_cui(mrconso_path, cui_set):
        cui = atom["cui"]
        atoms_by_cui.setdefault(cui, []).append(atom)

    # Step 3: Print results; use UMLS API for SNOMED/ICD10 when enabled
    api_lookup = None
    if use_api:
        try:
            from umls_cui_to_codes import lookup as api_lookup_fn
            api_lookup = api_lookup_fn
        except ImportError:
            print("(UMLS API unavailable; using local MRCONSO only)\n")

    for cui in sorted(atoms_by_cui.keys()):
        atoms = atoms_by_cui[cui]
        pref = next((a for a in atoms if a["ispref"] == "Y"), atoms[0])

        snomed: list[dict] = []
        icd10: list[dict] = []

        if api_lookup:
            try:
                api_result = api_lookup(cui)
                snomed = api_result.get("snomed", [])
                icd10 = api_result.get("icd10", [])
            except Exception as e:
                snomed = [a for a in atoms if a["sab"] in SNOMED_SABS]
                icd10 = [a for a in atoms if a["sab"] in ICD10_SABS]
                # Fall back to local; API error logged only when both empty
                if not snomed and not icd10:
                    print(f"\nCUI: {cui}  |  {pref['str']}")
                    print(f"  (API error: {e})")
                    continue
        else:
            snomed = [a for a in atoms if a["sab"] in SNOMED_SABS]
            icd10 = [a for a in atoms if a["sab"] in ICD10_SABS]

        print(f"\nCUI: {cui}  |  {pref['str']}")

        def _fmt(s: dict) -> tuple[str, str]:
            code = s.get("code", "")
            term = s.get("term") or s.get("str", "")
            return code, term[:55]

        def _print_codes(label: str, items: list[dict], pt_key: str, pt_val: str) -> None:
            if not items:
                print(f"  {label}:  (none)")
                return
            pt = next((x for x in items if x.get(pt_key) == pt_val), items[0])
            pt_mark = " [PT]" if pt.get(pt_key) == pt_val else ""
            code, term = _fmt(pt)
            print(f"  {label}:  {code:15} {term}{pt_mark}")
            for x in items:
                if x != pt:
                    c, t = _fmt(x)
                    print(f"           {c:15} {t}")

        is_api = bool(snomed and "term" in snomed[0]) or bool(icd10 and "term" in icd10[0])
        pt_key, pt_val = ("tty", "PT") if is_api else ("ispref", "Y")

        _print_codes("SNOMED", snomed, pt_key, pt_val)
        _print_codes("ICD-10", icd10, pt_key, pt_val)

        if show_all_sabs:
            all_sabs = sorted({a["sab"] for a in atoms})
            print(f"  All SABs: {', '.join(all_sabs)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test UMLS ER6 term-to-code lookup pattern.",
    )
    parser.add_argument(
        "word",
        nargs="?",
        default="bleeding",
        help="Word to look up (default: bleeding)",
    )
    parser.add_argument(
        "--meta",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "external_content"
        / "umls"
        / "2025AB"
        / "META",
        help="Path to UMLS META directory",
    )
    parser.add_argument(
        "--max-cui",
        type=int,
        default=20,
        help="Max concepts to return (default: 20)",
    )
    parser.add_argument(
        "--normalized",
        action="store_true",
        help="Use MRXNW_ENG (normalized word) instead of MRXW_ENG",
    )
    parser.add_argument(
        "--show-all-sabs",
        action="store_true",
        help="Print all source vocabularies (SABs) per concept for debugging",
    )
    parser.add_argument(
        "--no-api",
        action="store_true",
        help="Use only local MRCONSO; do not call UMLS API for SNOMED/ICD-10",
    )
    args = parser.parse_args()

    run_lookup(
        args.meta,
        args.word,
        max_cui=args.max_cui,
        use_normalized=args.normalized,
        show_all_sabs=args.show_all_sabs,
        use_api=not args.no_api,
    )


if __name__ == "__main__":
    main()
