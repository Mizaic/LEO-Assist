"""Scan pre-referral encounters for symptom/place surface form candidates.

Produces a review artifact:
  scripts/investigations/output/ngram_scan_results.json

The scan pipeline:
1) Read pre-referral encounters JSON.
2) Extract candidate 1-5 token n-grams from encounter text.
3) Batch-lookup exact Term/SurfaceForm matches via BATCH_EXACT_QUERY.
4) Keep only matches that belong to first_presentation concept set
   (symptoms + place_of_presentation with IS_A descendants).
5) Emit:
   - covered: phrases already resolvable to first_presentation concepts
   - unmapped_candidates: frequent phrases not yet mapped, with search hints
   - confirmed_additions: empty list for human review/edit before add script
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.queries.terminology import (
    BATCH_EXACT_QUERY,
    TERMINOLOGY_SEARCH,
)

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

INPUT_FILE = (
    ROOT / "scripts" / "investigations" / "output" / "pre_referral_encounters.json"
)
OUTPUT_FILE = (
    ROOT / "scripts" / "investigations" / "output" / "ngram_scan_results.json"
)

BATCH_SIZE = 500
MAX_NGRAM = 5
UNMAPPED_MIN_HITS = 4
MAX_UNMAPPED_FOR_SEARCH = 300
MAX_HIT_SAMPLES_PER_ITEM = 50

NEGATION_CUES = (
    "no ",
    "not ",
    "denies ",
    "denied ",
    "without ",
    "never ",
    "exclude ",
    "no evidence of ",
    "negative for ",
)

TOKEN_RE = re.compile(r"[a-z0-9&][a-z0-9&+/\-]*", re.IGNORECASE)
TIME_PREFIX_RE = re.compile(r"^\s*\d{1,2}:\d{2}\s*[-:]")
REQUEST_LINE_RE = re.compile(r"^\s*request for\b", re.IGNORECASE)
MEDICATION_LINE_RE = re.compile(
    r"\b(?:tablet|capsule|ml|mg|micrograms|inhaler|cream|ointment|foam)\b",
    re.IGNORECASE,
)
ADMIN_LINE_RE = re.compile(
    r"\b(?:scheduled task|summary care record|template version|access role|etp2)\b",
    re.IGNORECASE,
)

STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "to",
    "for",
    "in",
    "on",
    "at",
    "by",
    "with",
    "from",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "this",
    "that",
    "it",
    "as",
}

# Keep clinically relevant short acronyms even at 1-token ngram size.
ALLOWED_UNIGRAMS = {
    "a&e",
    "opd",
    "ooh",
    "ucc",
    "utc",
    "ldct",
    "tlhc",
    "pmb",
    "fit",
    "fobt",
    "hpv",
    "sob",
    "luts",
    "pr",
    "pv",
    "gp",
}

VALUESETS_Q = """
MATCH (d:AuditDomain)-[:HAS_SUBDOMAIN]->(v:ValueSet)
WHERE coalesce(d.episodeDetector, false) = true
  AND v.milestoneType = 'first_presentation'
RETURN v.id AS vs_id, v.name AS vs_name, v.rawJson AS raw_json
ORDER BY v.id
"""

ISA_Q = """
MATCH (ancestor:Concept)<-[:IS_A*1..5]-(d:Concept)
WHERE ancestor.id IN $ids AND d.active = true
RETURN ancestor.id AS parent_id, d.id AS child_id
"""


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _is_noise_line(line: str) -> bool:
    if not line.strip():
        return True
    if TIME_PREFIX_RE.search(line):
        return True
    if REQUEST_LINE_RE.search(line):
        return True
    if MEDICATION_LINE_RE.search(line) and "pain" not in line.lower():
        return True
    if ADMIN_LINE_RE.search(line):
        return True
    return False


def _phrase_assertion(raw_text: str, start_idx: int) -> str:
    left = raw_text[max(0, start_idx - 60) : start_idx].lower()
    for cue in NEGATION_CUES:
        if cue in left:
            return "absent"
    return "present"


def _extract_phrase_hits(text: str) -> list[tuple[str, int, str]]:
    """Return (ngram, start_char, assertion) for one encounter text."""
    hits: list[tuple[str, int, str]] = []

    for line in text.splitlines():
        if _is_noise_line(line):
            continue
        tokens = list(TOKEN_RE.finditer(line))
        if not tokens:
            continue

        words = [m.group(0).lower() for m in tokens]
        starts = [m.start() for m in tokens]

        for i in range(len(words)):
            for n in range(1, MAX_NGRAM + 1):
                j = i + n
                if j > len(words):
                    break
                phrase_tokens = words[i:j]
                phrase = " ".join(phrase_tokens).strip()
                if not phrase:
                    continue

                if n == 1:
                    w = phrase_tokens[0]
                    if w in STOPWORDS:
                        continue
                    if len(w) < 3 and w not in ALLOWED_UNIGRAMS:
                        continue
                else:
                    # Skip n-grams made only of stopwords.
                    if all(w in STOPWORDS for w in phrase_tokens):
                        continue

                assertion = _phrase_assertion(line, starts[i])
                hits.append((phrase, starts[i], assertion))
    return hits


def _chunked(seq: list[str], size: int) -> list[list[str]]:
    out: list[list[str]] = []
    for i in range(0, len(seq), size):
        out.append(seq[i : i + size])
    return out


def _load_first_presentation_concepts(
    kg: KnowledgeGraphClient,
) -> tuple[set[str], dict[str, str], dict[str, Any]]:
    """Return (concept_ids, concept_category, debug_meta)."""
    rows = kg.run(VALUESETS_Q) or []
    if not rows:
        return set(), {}, {"valuesets": []}

    parent_to_categories: dict[str, set[str]] = defaultdict(set)
    valueset_debug: list[dict[str, Any]] = []
    parent_ids: set[str] = set()

    for r in rows:
        vs_id = str(r.get("vs_id") or "")
        raw = r.get("raw_json")
        category = "place" if "place" in vs_id else "symptom"
        parents_this_vs: set[str] = set()
        try:
            vs_dict = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            vs_dict = {}

        for inc in (vs_dict.get("compose") or {}).get("include") or []:
            for c in inc.get("concept") or []:
                code = str(c.get("code") or "").strip()
                if not code:
                    continue
                parent_ids.add(code)
                parents_this_vs.add(code)
                parent_to_categories[code].add(category)

        valueset_debug.append(
            {
                "vs_id": vs_id,
                "vs_name": r.get("vs_name"),
                "parent_count": len(parents_this_vs),
            }
        )

    concept_ids: set[str] = set(parent_ids)
    concept_category: dict[str, str] = {}
    for pid, cats in parent_to_categories.items():
        concept_category[pid] = "both" if len(cats) > 1 else next(iter(cats))

    if parent_ids:
        desc_rows = kg.run(ISA_Q, ids=list(parent_ids)) or []
        for row in desc_rows:
            pid = str(row.get("parent_id") or "")
            cid = str(row.get("child_id") or "")
            if not cid:
                continue
            concept_ids.add(cid)
            if pid and pid in concept_category and cid not in concept_category:
                concept_category[cid] = concept_category[pid]

    debug_meta = {
        "valuesets": valueset_debug,
        "parent_count": len(parent_ids),
        "expanded_count": len(concept_ids),
    }
    return concept_ids, concept_category, debug_meta


def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")

    encounters: list[dict[str, Any]] = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    print(f"Loaded {len(encounters)} encounters from {INPUT_FILE}")

    # 1) Build n-gram hit inventory from encounter text
    ngram_counts: Counter[str] = Counter()
    ngram_hit_samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ngram_assert_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for idx, enc in enumerate(encounters, 1):
        text = str(enc.get("text") or "")
        if not text.strip():
            continue
        # De-duplicate per encounter to avoid repeated inflation in templated notes.
        seen_in_enc: set[tuple[str, str]] = set()
        for phrase, start, assertion in _extract_phrase_hits(text):
            k = (phrase, assertion)
            if k in seen_in_enc:
                continue
            seen_in_enc.add(k)
            ngram_counts[phrase] += 1
            ngram_assert_counts[phrase][assertion] += 1
            if len(ngram_hit_samples[phrase]) < MAX_HIT_SAMPLES_PER_ITEM:
                ngram_hit_samples[phrase].append(
                    {
                        "encounter_id": str(enc.get("encounter_id") or ""),
                        "patient_id": str(enc.get("patient_id") or ""),
                        "cancer_type": str(enc.get("cancer_type") or ""),
                        "referral_date": str(enc.get("referral_date") or ""),
                        "encounter_date": str(enc.get("encounter_date") or ""),
                        "assertion": assertion,
                        "char_start": start,
                    }
                )
        if idx % 2000 == 0:
            print(f"  processed {idx}/{len(encounters)} encounters")

    all_ngrams = sorted(ngram_counts.keys())
    print(f"Extracted {len(all_ngrams)} unique n-grams")

    kg = KnowledgeGraphClient()
    try:
        # 2) Load first_presentation concept set (parents + IS_A descendants)
        fp_concepts, concept_category, fp_debug = _load_first_presentation_concepts(kg)
        if not fp_concepts:
            raise RuntimeError(
                "No first_presentation concept set found. "
                "Check milestoneType on ValueSets and episodeDetector on domain."
            )
        print(
            "Loaded first_presentation concept set: "
            f"{fp_debug['expanded_count']} concepts "
            f"({fp_debug['parent_count']} parents)"
        )

        # 3) Batch exact lookup against Term/SurfaceForm indexes
        exact_hits_by_ngram: dict[str, list[dict[str, Any]]] = {}
        batches = _chunked(all_ngrams, BATCH_SIZE)
        for i, batch in enumerate(batches, 1):
            rows = kg.run(BATCH_EXACT_QUERY, normalized_terms=batch) or []
            for row in rows:
                ngram = str(row.get("input_term") or "")
                hits = list(row.get("hits") or [])
                # Keep only first_presentation concepts
                filtered = []
                for h in hits:
                    cid = str(h.get("concept_id") or "")
                    if cid in fp_concepts:
                        filtered.append(
                            {
                                "concept_id": cid,
                                "concept_fsn": h.get("fsn"),
                                "semantic_tag": h.get("semantic_tag"),
                                "score": h.get("score"),
                                "surface_form_status": h.get("surface_form_status", ""),
                                "category": concept_category.get(cid, "unknown"),
                            }
                        )
                if filtered:
                    filtered.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
                    exact_hits_by_ngram[ngram] = filtered
            if i % 20 == 0 or i == len(batches):
                print(f"  exact lookup batches: {i}/{len(batches)}")

        # 4) Build covered + unmapped lists
        covered: list[dict[str, Any]] = []
        unmapped_pool = []
        for ngram, count in ngram_counts.items():
            if ngram in exact_hits_by_ngram:
                best = exact_hits_by_ngram[ngram][0]
                covered.append(
                    {
                        "ngram": ngram,
                        "concept_id": best["concept_id"],
                        "concept_fsn": best.get("concept_fsn"),
                        "concept_category": best.get("category"),
                        "hit_count": int(count),
                        "assertion_present_count": int(
                            ngram_assert_counts[ngram].get("present", 0)
                        ),
                        "assertion_absent_count": int(
                            ngram_assert_counts[ngram].get("absent", 0)
                        ),
                        "encounter_hits": ngram_hit_samples[ngram],
                        "all_exact_hits": exact_hits_by_ngram[ngram],
                    }
                )
            elif count >= UNMAPPED_MIN_HITS:
                unmapped_pool.append((ngram, count))

        covered.sort(key=lambda x: x["hit_count"], reverse=True)
        unmapped_pool.sort(key=lambda x: x[1], reverse=True)

        # 5) Search hints for top unmapped candidates
        unmapped_candidates: list[dict[str, Any]] = []
        for ngram, count in unmapped_pool[:MAX_UNMAPPED_FOR_SEARCH]:
            try:
                search_rows = kg.run(TERMINOLOGY_SEARCH, q=ngram, limit=5) or []
            except Exception:
                search_rows = []
            unmapped_candidates.append(
                {
                    "ngram": ngram,
                    "hit_count": int(count),
                    "assertion_present_count": int(
                        ngram_assert_counts[ngram].get("present", 0)
                    ),
                    "assertion_absent_count": int(
                        ngram_assert_counts[ngram].get("absent", 0)
                    ),
                    "encounter_hits": ngram_hit_samples[ngram],
                    "terminology_search_results": [
                        {
                            "concept_id": r.get("snomed_concept_id"),
                            "fsn": r.get("term"),
                            "semantic_tag": r.get("semantic_tag"),
                            "score": r.get("score"),
                        }
                        for r in search_rows
                    ],
                }
            )

    finally:
        kg.close()

    output = {
        "summary": {
            "encounters_scanned": len(encounters),
            "unique_ngrams": len(all_ngrams),
            "covered_count": len(covered),
            "unmapped_count": len(unmapped_pool),
            "unmapped_with_search_hints": len(unmapped_candidates),
            "min_hits_for_unmapped": UNMAPPED_MIN_HITS,
        },
        "first_presentation_debug": fp_debug,
        "covered": covered,
        "unmapped_candidates": unmapped_candidates,
        # Human-reviewed entries should be appended here before script 2.
        # schema:
        # [{"ngram":"x", "concept_id":"123", "form":"X", "category":"symptom|place"}]
        "confirmed_additions": [],
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {OUTPUT_FILE}")
    print(
        "Summary:",
        output["summary"],
    )


if __name__ == "__main__":
    main()

