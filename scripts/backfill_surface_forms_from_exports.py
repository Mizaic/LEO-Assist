#!/usr/bin/env python3
"""Backfill SNOMED mapping synonyms from historical/exported training artifacts.

This script scans the export corpora, extracts candidate surface forms that are
anchored to a known SNOMED concept ID, and appends them to
`configs/snomed/snomed_ncda_*.json` as `guideline_synonyms`.

Safety rules:
- only concept-ID-anchored forms are considered
- no placeholders / obvious metadata tokens
- de-duplicated case-insensitively
- limited additions per concept to avoid config bloat
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs" / "snomed"
EXPORTS = ROOT / "exports"

MAPPING_GLOB = "snomed_ncda_*.json"

STOP_PHRASES = {
    "screening",
    "result",
    "procedure",
    "finding",
    "review",
    "clinic",
    "referral",
    "advice",
    "home visit",
}

NOISY_SUBSTRINGS = {
    "added from questionnaire",
    "new episode",
    "problem:",
    "date of first outpatient appointment",
    "seen in ",
    "reasons for request",
    "triaged ",
}

MONTH_TOKENS = {
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
}


def _norm(text: str) -> str:
    t = text.strip()
    t = re.sub(r"\s+", " ", t)
    t = t.replace("–", "-").replace("—", "-")
    return t


def _clean_candidate(text: str) -> str:
    t = _norm(text)
    t = re.sub(r"\[[A-Z_]+\]", "", t)
    t = re.sub(r"\s+", " ", t).strip(" -,:;.")
    t = re.sub(r"\s*\([A-Za-z0-9.]{3,8}\)\s*$", "", t)  # Read code trailer
    t = re.sub(r"^(Known|known|Probable|probable|Likely|likely)\s+", "", t)
    return t


def _is_valid_form(text: str) -> bool:
    t = text.strip()
    low = t.lower()
    if len(t) < 3 or len(t) > 96:
        return False
    if low in STOP_PHRASES:
        return False
    if "[" in t or "]" in t:
        return False
    if ":" in t:
        return False
    if any(s in low for s in NOISY_SUBSTRINGS):
        return False
    if not re.search(r"[A-Za-z]", t):
        return False
    if len(t.split()) > 7:
        return False
    if any(tok in MONTH_TOKENS for tok in re.findall(r"[a-z]+", low)):
        return False
    if len(re.findall(r"\d", t)) > 4:
        return False
    if re.search(r"(canc|tumou|clin|haema|gynae|childrens t)$", low):
        return False
    if re.fullmatch(r"[A-Z0-9.\-/ ]+", t) and len(t) <= 12:
        return False
    if re.fullmatch(r"[0-9.\-/ ]+", t):
        return False
    return True


@dataclass
class MappingEntryRef:
    file_path: Path
    mapping_key: str


def build_concept_index() -> tuple[dict[str, list[MappingEntryRef]], dict[str, set[str]]]:
    concept_to_entries: dict[str, list[MappingEntryRef]] = defaultdict(list)
    concept_to_existing_forms: dict[str, set[str]] = defaultdict(set)

    for fp in sorted(CONFIG_DIR.glob(MAPPING_GLOB)):
        if not fp.is_file():
            continue
        payload = json.loads(fp.read_text(encoding="utf-8"))
        mappings = payload.get("mappings", {})
        for key, obj in mappings.items():
            if not isinstance(obj, dict):
                continue
            cid = str(obj.get("concept_id", "")).strip()
            if not cid:
                continue
            concept_to_entries[cid].append(MappingEntryRef(fp, key))
            forms = [key, obj.get("preferred_term", "")]
            forms.extend(obj.get("guideline_synonyms") or [])
            concept_to_existing_forms[cid].update(
                _clean_candidate(f).lower() for f in forms if _clean_candidate(str(f))
            )
    return concept_to_entries, concept_to_existing_forms


def _extract_concept_text_pairs_from_obj(obj: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []

    # Old format: top-level concept_id + text
    top_cid = str(obj.get("concept_id", "")).strip()
    top_txt = str(obj.get("text", "")).strip()
    if top_cid and top_txt:
        out.append((top_cid, top_txt))

    # Entity arrays with nested normalised_code
    ents = obj.get("entities")
    if isinstance(ents, list):
        for e in ents:
            if not isinstance(e, dict):
                continue
            txt = str(e.get("text", "")).strip()
            if not txt:
                continue
            cid = ""
            if isinstance(e.get("normalised_code"), dict):
                cid = str(e["normalised_code"].get("code", "")).strip()
            if not cid:
                cid = str(e.get("snomed_id", "")).strip()
            if cid:
                out.append((cid, txt))

    return out


def iter_source_files() -> list[Path]:
    files: list[Path] = []
    # User-requested sources
    files.extend((EXPORTS / "training" / "old").glob("*.jsonl"))
    files.extend((EXPORTS / "ner" / "all_domains" / "archive_pre_refactor").glob("domain_entities_*.jsonl"))
    files.extend((EXPORTS / "ner" / "all_domains").glob("domain_*.jsonl"))
    files.extend((EXPORTS / "ner" / "runs" / "20260228_161535").glob("domain_*.jsonl"))
    files.append(EXPORTS / "ner" / "training" / "exclusion_domain_v1.jsonl")
    # training_adapters JSONL does not carry concept IDs; intentionally skipped.
    return [f for f in files if f.exists() and f.is_file()]


def collect_candidates() -> tuple[dict[str, Counter], dict[str, set[str]]]:
    by_concept: dict[str, Counter] = defaultdict(Counter)
    by_concept_sources: dict[str, set[str]] = defaultdict(set)
    for fp in iter_source_files():
        with fp.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for cid, txt in _extract_concept_text_pairs_from_obj(obj):
                    form = _clean_candidate(txt)
                    if not _is_valid_form(form):
                        continue
                    by_concept[cid][form] += 1
                    by_concept_sources[cid].add(fp.name)
    return by_concept, by_concept_sources


def apply_backfill(
    *,
    dry_run: bool,
    min_count: int,
    max_per_concept: int,
    report_path: Path,
) -> dict[str, Any]:
    concept_to_entries, concept_to_existing = build_concept_index()
    candidates, candidate_sources = collect_candidates()

    report: dict[str, Any] = {
        "min_count": min_count,
        "max_per_concept": max_per_concept,
        "concepts_scanned": len(candidates),
        "concepts_updated": 0,
        "synonyms_added": 0,
        "files_updated": 0,
        "updates": {},
    }

    file_payload_cache: dict[Path, dict[str, Any]] = {}
    touched_files: set[Path] = set()

    for cid, counter in candidates.items():
        refs = concept_to_entries.get(cid)
        if not refs:
            continue
        existing = concept_to_existing.get(cid, set())

        ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0].lower()))
        accepted: list[str] = []
        for form, cnt in ranked:
            if cnt < min_count:
                continue
            low = form.lower()
            if low in existing:
                continue
            accepted.append(form)
            existing.add(low)
            if len(accepted) >= max_per_concept:
                break

        if not accepted:
            continue

        # Apply to the first mapping entry for this concept (deterministic).
        ref = refs[0]
        if ref.file_path not in file_payload_cache:
            file_payload_cache[ref.file_path] = json.loads(ref.file_path.read_text(encoding="utf-8"))
        payload = file_payload_cache[ref.file_path]
        mapping_obj = payload["mappings"][ref.mapping_key]
        syns = list(mapping_obj.get("guideline_synonyms") or [])
        syn_low = {_clean_candidate(s).lower() for s in syns if _clean_candidate(str(s))}
        for s in accepted:
            if s.lower() not in syn_low:
                syns.append(s)
                syn_low.add(s.lower())
        mapping_obj["guideline_synonyms"] = syns
        mapping_obj["guideline_synonym_count"] = len(syns)

        report["concepts_updated"] += 1
        report["synonyms_added"] += len(accepted)
        report["updates"][cid] = {
            "target_file": str(ref.file_path.relative_to(ROOT)),
            "mapping_key": ref.mapping_key,
            "added": accepted,
            "candidate_sources": sorted(candidate_sources.get(cid, set())),
        }
        touched_files.add(ref.file_path)

    if not dry_run:
        for fp, payload in file_payload_cache.items():
            fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["files_updated"] = len(touched_files)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--min-count", type=int, default=2)
    p.add_argument("--max-per-concept", type=int, default=8)
    p.add_argument(
        "--report",
        type=Path,
        default=ROOT / "exports" / "ner" / "surface_form_backfill_report.json",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    report = apply_backfill(
        dry_run=args.dry_run,
        min_count=args.min_count,
        max_per_concept=args.max_per_concept,
        report_path=args.report,
    )
    print(json.dumps(
        {
            "dry_run": args.dry_run,
            "concepts_updated": report["concepts_updated"],
            "synonyms_added": report["synonyms_added"],
            "files_updated": report["files_updated"],
            "report": str(args.report),
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
