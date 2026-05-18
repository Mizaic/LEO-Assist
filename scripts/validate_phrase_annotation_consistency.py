"""Flag inconsistent phrase annotations in verified training gold labels.

This script scans repeated entity phrases in the current GoldLabel training set
and reports where the same phrase is annotated with different label and/or
assertion combinations.

Default source is Neo4j GoldLabel nodes linked from completed TrainingCandidate
records, matching the active training pool used by export tooling.

Examples
--------
python scripts/validate_phrase_annotation_consistency.py
python scripts/validate_phrase_annotation_consistency.py --phrase "suspected cancer"
python scripts/validate_phrase_annotation_consistency.py --min-occurrences 3
python scripts/validate_phrase_annotation_consistency.py --fail-on-conflict
python scripts/validate_phrase_annotation_consistency.py --write-json /tmp/conflicts.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import KnowledgeGraphClient

_GET_TRAINING_GOLD_LABELS = """
MATCH (c:TrainingCandidate)-[:PRODUCED]->(g:GoldLabel)
WHERE c.status = 'completed'
  AND g.entities_json IS NOT NULL
  AND coalesce(g.frozen_golden_set, false) = false
RETURN
  g.label_id AS label_id,
  g.text AS text,
  g.entities_json AS entities_json,
  g.source AS source
ORDER BY g.created_at ASC
"""

_LIST_PHRASE_MULTILABEL_APPROVALS = """
MATCH (p:PhraseMultiLabelApproval)
RETURN p.phrase_norm AS phrase_norm, coalesce(p.allowed_labels, []) AS allowed_labels
"""

_APPROVED_MULTI_LABEL_PHRASES: dict[str, set[str]] = {
    "2ww breast": {"PROCEDURE", "SITUATION"},
    "2ww gynae": {"PROCEDURE", "SITUATION"},
    "2ww gynaecology": {"PROCEDURE", "SITUATION"},
    "2ww head and neck": {"PROCEDURE", "SITUATION"},
    "2ww referral": {"PROCEDURE", "SITUATION"},
}


def _normalise_phrase(text: str) -> str:
    compact = re.sub(r"\s+", " ", text.strip())
    return compact.lower()


def _normalise_label(entity: dict[str, Any]) -> str:
    return str(entity.get("label") or entity.get("semantic_tag") or "UNKNOWN").upper()


def _normalise_assertion(entity: dict[str, Any]) -> str:
    raw = str(entity.get("assertion") or "present").strip().lower()
    return raw or "present"


@dataclass(frozen=True)
class Occurrence:
    phrase: str
    label: str
    assertion: str
    span_length: int
    label_id: str
    source: str
    sentence_preview: str


def _iter_gold_rows(limit: int | None = None) -> Iterable[dict[str, Any]]:
    try:
        load_keyvault_secrets()
    except ModuleNotFoundError:
        # Local fallback for environments without azure-* extras installed.
        pass

    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            rows = [dict(row) for row in session.run(_GET_TRAINING_GOLD_LABELS)]
    finally:
        client.close()

    if limit is None or limit <= 0:
        return rows
    return rows[:limit]


def _load_phrase_multilabel_policy() -> dict[str, set[str]]:
    policy = {k: set(v) for k, v in _APPROVED_MULTI_LABEL_PHRASES.items()}
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            rows = [dict(r) for r in session.run(_LIST_PHRASE_MULTILABEL_APPROVALS)]
    except Exception:
        return policy
    finally:
        client.close()
    for row in rows:
        phrase = _normalise_phrase(str(row.get("phrase_norm") or ""))
        if not phrase:
            continue
        labels = {
            str(label).strip().upper() for label in (row.get("allowed_labels") or [])
        }
        labels = {label for label in labels if label}
        if len(labels) >= 2:
            policy[phrase] = labels
    return policy


def _safe_parse_entities(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    if not isinstance(raw, str):
        return []
    text = raw.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [e for e in parsed if isinstance(e, dict)]


def _build_occurrences(
    rows: Iterable[dict[str, Any]],
    phrase_filter: str | None = None,
) -> list[Occurrence]:
    needles = _normalise_phrase(phrase_filter) if phrase_filter else None
    out: list[Occurrence] = []
    for row in rows:
        label_id = str(row.get("label_id") or "")
        source = str(row.get("source") or "")
        sentence = str(row.get("text") or "")
        preview = sentence[:140].replace("\n", " ")
        for ent in _safe_parse_entities(row.get("entities_json")):
            phrase_raw = str(ent.get("text") or "").strip()
            if not phrase_raw:
                continue
            phrase = _normalise_phrase(phrase_raw)
            if needles and needles not in phrase:
                continue
            start = int(ent.get("start") or 0)
            end = int(ent.get("end") or 0)
            span_length = max(0, end - start)
            out.append(
                Occurrence(
                    phrase=phrase,
                    label=_normalise_label(ent),
                    assertion=_normalise_assertion(ent),
                    span_length=span_length,
                    label_id=label_id,
                    source=source,
                    sentence_preview=preview,
                )
            )
    return out


def _format_signature(label: str, assertion: str) -> str:
    return f"{label} | {assertion}"


def _is_approved_multilabel_phrase(phrase: str, labels: set[str]) -> bool:
    allowed = _APPROVED_MULTI_LABEL_PHRASES.get(phrase)
    return bool(allowed and len(labels) > 1 and labels.issubset(allowed))


def _build_conflict_report(
    occurrences: list[Occurrence],
    min_occurrences: int,
    max_examples: int,
    policy: dict[str, set[str]],
) -> tuple[list[dict[str, Any]], int, int, int]:
    by_phrase: dict[str, list[Occurrence]] = defaultdict(list)
    for occ in occurrences:
        by_phrase[occ.phrase].append(occ)

    conflicts: list[dict[str, Any]] = []
    assertion_only_variants = 0
    approved_multilabel_variants = 0
    for phrase, group in by_phrase.items():
        if len(group) < min_occurrences:
            continue
        signature_counts: Counter[str] = Counter(
            _format_signature(g.label, g.assertion) for g in group
        )
        label_count = len({g.label for g in group})
        assertion_count = len({g.assertion for g in group})
        labels = {g.label for g in group}
        if label_count <= 1:
            if assertion_count > 1:
                assertion_only_variants += 1
            continue
        allowed = policy.get(phrase)
        if allowed and len(labels) > 1 and labels.issubset(allowed):
            approved_multilabel_variants += 1
            continue

        grouped_examples: dict[str, list[Occurrence]] = defaultdict(list)
        for item in group:
            grouped_examples[_format_signature(item.label, item.assertion)].append(item)

        example_rows: list[dict[str, str]] = []
        for signature, sig_items in sorted(
            grouped_examples.items(),
            key=lambda kv: (-len(kv[1]), kv[0]),
        ):
            for ex in sig_items[:max_examples]:
                example_rows.append(
                    {
                        "signature": signature,
                        "label_id": ex.label_id,
                        "source": ex.source,
                        "span_length": str(ex.span_length),
                        "sentence_preview": ex.sentence_preview,
                    }
                )
            if len(example_rows) >= max_examples:
                break

        conflicts.append(
            {
                "phrase": phrase,
                "occurrences": len(group),
                "distinct_labels": label_count,
                "distinct_assertions": assertion_count,
                "signature_counts": dict(signature_counts.most_common()),
                "examples": example_rows[:max_examples],
            }
        )

    conflicts.sort(key=lambda item: (-int(item["occurrences"]), item["phrase"]))
    return (
        conflicts,
        len(by_phrase),
        assertion_only_variants,
        approved_multilabel_variants,
    )


def _print_report(
    *,
    total_rows: int,
    total_occurrences: int,
    total_unique_phrases: int,
    conflicts: list[dict[str, Any]],
    assertion_only_variants: int,
    approved_multilabel_variants: int,
    top: int,
) -> None:
    print("Phrase annotation consistency report")
    print("=" * 36)
    print(f"Gold labels scanned      : {total_rows}")
    print(f"Entity occurrences       : {total_occurrences}")
    print(f"Unique phrases           : {total_unique_phrases}")
    print(f"Conflicting phrases      : {len(conflicts)}")
    print(f"Assertion-only variants  : {assertion_only_variants}")
    print(f"Approved multi-label     : {approved_multilabel_variants}")
    print("")
    if not conflicts:
        print("No phrase-level label/assertion conflicts found.")
        return

    print(f"Top conflicts (showing {min(top, len(conflicts))})")
    print("-" * 36)
    for idx, conflict in enumerate(conflicts[:top], start=1):
        phrase = str(conflict["phrase"])
        print(
            f"{idx}. '{phrase}' "
            f"(occurrences={conflict['occurrences']}, "
            f"labels={conflict['distinct_labels']}, "
            f"assertions={conflict['distinct_assertions']})"
        )
        for signature, count in conflict["signature_counts"].items():
            print(f"   - {signature}: {count}")
        for ex in conflict.get("examples", [])[:3]:
            print(
                "     example: "
                f"{ex['signature']} "
                f"[label_id={ex['label_id'][:12]} source={ex['source']}] "
                f"{ex['sentence_preview']}"
            )
        print("")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate phrase-level label/assertion consistency in training gold labels."
    )
    parser.add_argument(
        "--phrase",
        default=None,
        help="Only inspect phrases containing this substring (case-insensitive).",
    )
    parser.add_argument(
        "--min-occurrences",
        type=int,
        default=2,
        help="Minimum occurrences for a phrase before evaluating conflicts.",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=5,
        help="Maximum example rows captured per conflicting phrase.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=25,
        help="How many conflicting phrases to print in the console report.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional cap on number of gold labels scanned (0 = all).",
    )
    parser.add_argument(
        "--write-json",
        default="",
        help="Optional output path for full JSON conflict payload.",
    )
    parser.add_argument(
        "--fail-on-conflict",
        action="store_true",
        help="Return non-zero exit code when any conflict is found.",
    )
    args = parser.parse_args()

    rows = list(_iter_gold_rows(limit=args.limit if args.limit > 0 else None))
    occurrences = _build_occurrences(rows, phrase_filter=args.phrase)
    policy = _load_phrase_multilabel_policy()
    (
        conflicts,
        unique_phrase_count,
        assertion_only_variants,
        approved_multilabel_variants,
    ) = _build_conflict_report(
        occurrences=occurrences,
        min_occurrences=max(1, args.min_occurrences),
        max_examples=max(1, args.max_examples),
        policy=policy,
    )

    _print_report(
        total_rows=len(rows),
        total_occurrences=len(occurrences),
        total_unique_phrases=unique_phrase_count,
        conflicts=conflicts,
        assertion_only_variants=assertion_only_variants,
        approved_multilabel_variants=approved_multilabel_variants,
        top=max(1, args.top),
    )

    if args.write_json:
        payload = {
            "summary": {
                "gold_labels_scanned": len(rows),
                "entity_occurrences": len(occurrences),
                "unique_phrases": unique_phrase_count,
                "conflicting_phrases": len(conflicts),
                "assertion_only_variants": assertion_only_variants,
                "approved_multilabel_variants": approved_multilabel_variants,
            },
            "conflicts": conflicts,
        }
        out_path = Path(args.write_json).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"JSON report written to: {out_path}")

    if args.fail_on_conflict and conflicts:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
