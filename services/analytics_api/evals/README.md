# Case Finding Eval Set

`case_finding_gold_queries.jsonl` is the seed judgment set for encounter
retrieval quality tracking.

## Purpose

- Anchor quarter-over-quarter retrieval quality changes.
- Provide representative symptom-bundle and referral-pattern queries.
- Support nDCG, Recall@K, and Precision@K comparisons.

## JSONL schema

- `query_id`: stable identifier.
- `query_text`: analyst-style natural-language query.
- `priority`: critical/high/medium.
- `relevant_terms`: expected lexical anchors for relevant encounters.
- `negative_terms`: anti-signals for likely false positives.
- `notes`: clinical context.

## Next step

Augment with real labeled `encounter_id` judgments from analyst review sessions.
