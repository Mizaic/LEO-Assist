"""Audit gold-label span token lengths vs. spancat suggester sizes.

Queries the Knowledge Graph for all completed GoldLabel records, tokenises
each entity span with a simple whitespace splitter (matching spaCy's default
English tokeniser closely enough for length estimates), and reports:

1. Per-label histogram of token counts
2. Spans exceeding a given threshold (default 5 -- current ngram_suggester max)
3. Summary of how many training examples are silently dropped per label
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient


CURRENT_MAX_NGRAM = 5

QUERY = """
MATCH (c:TrainingCandidate)-[:PRODUCED]->(g:GoldLabel)
WHERE c.status = 'completed'
  AND g.entities_json IS NOT NULL
RETURN
    g.label_id AS label_id,
    g.text AS text,
    g.entities_json AS entities_json
"""


def _token_count(text: str) -> int:
    """Approximate token count using whitespace split."""
    return len(text.split())


def main() -> None:
    kg = KnowledgeGraphClient()
    rows = kg.run(QUERY)
    print(f"Fetched {len(rows)} gold-label records from Knowledge Graph.\n")

    label_lengths: dict[str, list[int]] = defaultdict(list)
    over_limit: list[dict] = []
    total_spans = 0
    total_records = 0

    for row in rows:
        entities_raw = row.get("entities_json")
        if not entities_raw:
            continue
        try:
            entities = json.loads(entities_raw)
        except (json.JSONDecodeError, TypeError):
            continue

        total_records += 1
        text = row.get("text", "")

        for ent in entities:
            label = str(ent.get("label", ent.get("semantic_tag", "UNKNOWN")))
            ent_text = str(ent.get("text", ""))
            if not ent_text:
                start = int(ent.get("start", 0))
                end = int(ent.get("end", 0))
                ent_text = text[start:end] if 0 <= start < end <= len(text) else ""
            if not ent_text:
                continue

            n_tokens = _token_count(ent_text)
            total_spans += 1
            label_lengths[label.upper()].append(n_tokens)

            if n_tokens > CURRENT_MAX_NGRAM:
                over_limit.append({
                    "label": label.upper(),
                    "tokens": n_tokens,
                    "text": ent_text[:120],
                    "label_id": row.get("label_id", ""),
                })

    print(f"Total records: {total_records}")
    print(f"Total entity spans: {total_spans}")
    print(f"Current ngram_suggester max: {CURRENT_MAX_NGRAM} tokens")
    print()

    print("=" * 80)
    print("PER-LABEL TOKEN LENGTH DISTRIBUTION")
    print("=" * 80)

    for label in sorted(label_lengths.keys()):
        lengths = label_lengths[label]
        counter = Counter(lengths)
        n_over = sum(1 for l in lengths if l > CURRENT_MAX_NGRAM)
        pct_over = (n_over / len(lengths) * 100) if lengths else 0
        max_len = max(lengths) if lengths else 0

        print(f"\n{label} ({len(lengths)} spans, {n_over} over limit = {pct_over:.1f}%)")
        for tok_count in sorted(counter.keys()):
            bar = "#" * min(counter[tok_count], 60)
            marker = " <<<" if tok_count > CURRENT_MAX_NGRAM else ""
            print(f"  {tok_count:3d} tokens: {counter[tok_count]:5d} {bar}{marker}")
        if max_len > CURRENT_MAX_NGRAM:
            print(f"  ** Max token length: {max_len} -- EXCEEDS ngram limit **")

    print()
    print("=" * 80)
    print(f"SPANS EXCEEDING {CURRENT_MAX_NGRAM} TOKENS ({len(over_limit)} total)")
    print("=" * 80)

    over_by_label = defaultdict(list)
    for item in over_limit:
        over_by_label[item["label"]].append(item)

    for label in sorted(over_by_label.keys()):
        items = over_by_label[label]
        print(f"\n{label} ({len(items)} spans over limit):")
        seen_texts: set[str] = set()
        for item in sorted(items, key=lambda x: -x["tokens"]):
            key = item["text"].strip().lower()
            if key in seen_texts:
                continue
            seen_texts.add(key)
            print(f"  [{item['tokens']:2d} tok] {item['text']}")

    print()
    print("=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    all_lengths = [l for lengths in label_lengths.values() for l in lengths]
    if all_lengths:
        p95 = sorted(all_lengths)[int(len(all_lengths) * 0.95)]
        p99 = sorted(all_lengths)[int(len(all_lengths) * 0.99)]
        mx = max(all_lengths)
        print(f"  p95 span length: {p95} tokens")
        print(f"  p99 span length: {p99} tokens")
        print(f"  max span length: {mx} tokens")
        suggested = min(max(p99, 6), 15)
        print(f"  Suggested ngram_range_suggester max_size: {suggested}")
    print()


if __name__ == "__main__":
    main()
