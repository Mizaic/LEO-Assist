"""Backfill DOCUMENTS relationships for first_presentation concepts.

Reads:
  - scripts/investigations/output/pre_referral_encounters.json
  - scripts/investigations/output/ngram_scan_results.json

Builds phrase -> concept mappings from:
  1) covered entries (already resolvable phrases)
  2) confirmed_additions entries (human-reviewed new forms)

Then rescans encounters and writes:
  (e:Encounter)-[:DOCUMENTS {assertion, source, confidence, evidence}]->(c:Concept)

Rules:
  - symptom category writes only when assertion == "present"
  - place category writes for both present/absent

Dry-run by default.
Use --apply to commit writes.
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
from libs.neo4j_client.client import PatientGraphClient

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

APPLY = "--apply" in sys.argv

ENCOUNTERS_FILE = (
    ROOT / "scripts" / "investigations" / "output" / "pre_referral_encounters.json"
)
SCAN_RESULTS_FILE = (
    ROOT / "scripts" / "investigations" / "output" / "ngram_scan_results.json"
)

MAX_NGRAM = 5
TOKEN_RE = re.compile(r"[a-z0-9&][a-z0-9&+/\-]*", re.IGNORECASE)

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

_UPSERT_DOCUMENTS_Q = """
MATCH (e:Encounter)
WHERE toString(e.id) = $encounter_id
OPTIONAL MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e)
OPTIONAL MATCH (c:Concept {id: $concept_id})
MERGE (s:Clinical_finding {conceptId: toInteger($concept_id)})
SET s.updated_at = datetime(),
    s.created_at = coalesce(s.created_at, datetime()),
    s.name = coalesce(c.fsn, c.name, s.name, toString($concept_id)),
    s.semanticTag = coalesce(c.semantic_tag, s.semanticTag, 'Clinical_finding')
MERGE (e)-[r:DOCUMENTS {conceptId: toInteger($concept_id)}]->(s)
ON CREATE SET r.created_at = datetime()
SET r.assertion = $assertion,
    r.source = 'surface_form_backfill',
    r.confidence = 0.85,
    r.evidence = $evidence,
    r.coded_at = datetime()
FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
    MERGE (p)-[:HAS_FINDING]->(s)
)
RETURN toString(e.id) AS encounter_id, toString(s.conceptId) AS concept_id
"""


def _normalize(text: str) -> str:
    return " ".join(str(text or "").lower().strip().split())


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


def _assertion_for_position(raw_line: str, start_idx: int) -> str:
    left = raw_line[max(0, start_idx - 60) : start_idx].lower()
    for cue in NEGATION_CUES:
        if cue in left:
            return "absent"
    return "present"


def _extract_phrase_hits(text: str) -> list[tuple[str, str]]:
    """Return list of (phrase, assertion) for one encounter text."""
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
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
                phrase = " ".join(words[i:j]).strip()
                if not phrase:
                    continue
                assertion = _assertion_for_position(line, starts[i])
                k = (phrase, assertion)
                if k in seen:
                    continue
                seen.add(k)
                out.append(k)
    return out


def _load_form_map() -> dict[str, list[dict[str, str]]]:
    payload = json.loads(SCAN_RESULTS_FILE.read_text(encoding="utf-8"))
    form_map: dict[str, list[dict[str, str]]] = defaultdict(list)

    for item in payload.get("covered", []):
        ngram = _normalize(str(item.get("ngram") or ""))
        concept_id = str(item.get("concept_id") or "")
        category = str(item.get("concept_category") or "unknown")
        if ngram and concept_id:
            form_map[ngram].append({"concept_id": concept_id, "category": category})

    for item in payload.get("confirmed_additions", []):
        form = _normalize(str(item.get("form") or item.get("ngram") or ""))
        concept_id = str(item.get("concept_id") or "")
        category = str(item.get("category") or "unknown")
        if form and concept_id:
            form_map[form].append({"concept_id": concept_id, "category": category})

    # dedupe per form/concept pair
    deduped: dict[str, list[dict[str, str]]] = {}
    for form, entries in form_map.items():
        seen: set[tuple[str, str]] = set()
        kept = []
        for e in entries:
            key = (e["concept_id"], e["category"])
            if key in seen:
                continue
            seen.add(key)
            kept.append(e)
        deduped[form] = kept
    return deduped


def main() -> None:
    if not ENCOUNTERS_FILE.exists():
        raise FileNotFoundError(f"Missing encounters file: {ENCOUNTERS_FILE}")
    if not SCAN_RESULTS_FILE.exists():
        raise FileNotFoundError(f"Missing scan output file: {SCAN_RESULTS_FILE}")

    encounters: list[dict[str, Any]] = json.loads(
        ENCOUNTERS_FILE.read_text(encoding="utf-8")
    )
    form_map = _load_form_map()
    if not form_map:
        print(
            "No form mappings found in covered/confirmed_additions; nothing to backfill."
        )
        return

    print(
        f"Loaded {len(encounters)} encounters and {len(form_map)} mapped phrases; "
        f"mode={'APPLY' if APPLY else 'DRY RUN'}"
    )

    writes: list[dict[str, str]] = []
    per_concept = Counter()
    per_assertion = Counter()

    for idx, enc in enumerate(encounters, 1):
        enc_id = str(enc.get("encounter_id") or "")
        text = str(enc.get("text") or "")
        if not enc_id or not text.strip():
            continue
        phrase_hits = _extract_phrase_hits(text)
        for phrase, assertion in phrase_hits:
            if phrase not in form_map:
                continue
            for mapping in form_map[phrase]:
                category = mapping["category"]
                # Symptoms only keep present assertions.
                if category == "symptom" and assertion != "present":
                    continue
                concept_id = mapping["concept_id"]
                writes.append(
                    {
                        "encounter_id": enc_id,
                        "concept_id": concept_id,
                        "assertion": assertion,
                        "evidence": phrase[:200],
                        "category": category,
                    }
                )
                per_concept[concept_id] += 1
                per_assertion[assertion] += 1
        if idx % 2000 == 0:
            print(f"  scanned {idx}/{len(encounters)} encounters")

    # De-duplicate exact write triplets so MERGE load is smaller.
    dedup: dict[tuple[str, str, str], dict[str, str]] = {}
    for w in writes:
        key = (w["encounter_id"], w["concept_id"], w["assertion"])
        if key not in dedup:
            dedup[key] = w
    final_writes = list(dedup.values())

    print(
        f"Prepared {len(final_writes)} unique DOCUMENTS upserts "
        f"({len(writes)} raw hits before dedupe)."
    )
    print(f"Assertion split: {dict(per_assertion)}")
    print(f"Top concepts: {per_concept.most_common(10)}")

    if not APPLY:
        print("Dry run complete. Re-run with --apply to write DOCUMENTS relationships.")
        return

    pg = PatientGraphClient()
    ok = 0
    try:
        for i, w in enumerate(final_writes, 1):
            rows = (
                pg.run(
                    _UPSERT_DOCUMENTS_Q,
                    encounter_id=w["encounter_id"],
                    concept_id=w["concept_id"],
                    assertion=w["assertion"],
                    evidence=w["evidence"],
                )
                or []
            )
            if rows:
                ok += 1
            if i % 2000 == 0:
                print(f"  wrote {i}/{len(final_writes)}")
    finally:
        pg.close()

    print(f"Done. Successful writes: {ok}/{len(final_writes)}")


if __name__ == "__main__":
    main()
