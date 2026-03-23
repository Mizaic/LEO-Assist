# Training Data Pipeline Evaluation Report

Generated: 2026-03-05 13:45:00 UTC

Duration: 3689s


## Run Metadata

| Parameter | Value |
|---|---|
| Extractor backend | `llm/arn:aws:bedrock:eu-west-2:204065380870:inference-profile/eu.anthropic.claude-haiku-4-5-20251001-v1:0 vbedrock-1.0` |
| Post-processor rules loaded | 23 |
| Coding mode | `hitl` |
| Min score threshold | 0.5 |
| Confidence flag threshold | 0.6 |
| Eval limit | none (all records) |
| Terminology API instance(s) | `http://localhost:8001` · `http://localhost:8011` · `http://localhost:8021` |
| ConText assertion detection | enabled |

## Pipeline Summary

| Metric | Value |
|---|---|
| Records fetched | 12656 |
| Records written back | 12656 |
| Records errored | 0 |
| Total entities extracted | 13186 |
| Entities coded (score >= 0.5) | 13181 (100.0%) |
| Tier 1 — auto_coded | 9433 |
| Tier 2 — coded_with_flag / route_to_review | 575 |
| Tier 3 — route_to_review / not_coded | 3178 |
| Unique surface form gaps | 4 |
| Unique low-confidence terms | 0 |

### Assertion Distribution

| Assertion | Count |
|---|---|
| `present` | 9709 |
| `absent` | 1714 |
| `hypothetical` | 799 |
| `historical` | 442 |
| `possible` | 410 |
| `family` | 70 |
| `declined` | 37 |
| `refuted` | 5 |

## Surface Form Gaps

Entities the pipeline extracted but the terminology API could not code (top score < 0.5). These indicate missing surface forms in the terminology graph and are the primary actionable output of this report.

| Occurrences | Entity text | Label | Top candidate | Top score |
|---|---|---|---|---|
| 1 | `overtreated` | `finding` | *(no match)* | 0.0 |
| 1 | `cosmocol` | `substance` | *(no match)* | 0.0 |
| 1 | `stopped diannette a year ago` | `substance` | *(no match)* | 0.0 |
| 1 | `Dry Giloy` | `substance` | *(no match)* | 0.0 |

## Low-Confidence Extractions

Pipeline entities with extraction confidence < 0.6. These are candidates for HITL review.

*No low-confidence extractions (all entities >= 0.6).*


## Per-Record Detail

Top 30 records by surface form gap count. Shows entities written to `entities_json`.

### `59603d1cd98cfba1366a39b08562708e` (source: seed, quality: 0.33)

- Entities: 3 | Coded: 2 | T1: 2 T2: 0 T3: 1 | Surface gaps: 1 | Written: yes

**Surface form gaps in this record:**

| text | label | top score | top candidate |
|---|---|---|---|
| `overtreated` | `finding` | 0.0 | *(no match)* |

### `f06351a19ff3e934e72730a0cda21d83` (source: anchor_mining, quality: 1.00)

- Entities: 2 | Coded: 1 | T1: 0 T2: 0 T3: 2 | Surface gaps: 1 | Written: yes

**Surface form gaps in this record:**

| text | label | top score | top candidate |
|---|---|---|---|
| `cosmocol` | `substance` | 0.0 | *(no match)* |

### `bd06166a86d59475daf4d3076adc39bf` (source: anchor_mining, quality: 1.00)

- Entities: 7 | Coded: 6 | T1: 2 T2: 4 T3: 1 | Surface gaps: 1 | Written: yes

**Surface form gaps in this record:**

| text | label | top score | top candidate |
|---|---|---|---|
| `stopped diannette a year ago` | `substance` | 0.0 | *(no match)* |

### `95fa23d20864da4b30e97bf7fae67e06` (source: anchor_mining, quality: 1.00)

- Entities: 2 | Coded: 1 | T1: 1 T2: 0 T3: 1 | Surface gaps: 1 | Written: yes

**Surface form gaps in this record:**

| text | label | top score | top candidate |
|---|---|---|---|
| `Dry Giloy` | `substance` | 0.0 | *(no match)* |

### `f1c2f877e4e18af69f3d7043e583e57f` (source: seed, quality: 0.60)

- Entities: 5 | Coded: 5 | T1: 2 T2: 1 T3: 2 | Surface gaps: 0 | Written: yes

### `fe7213b1283313d192c5b8c213eccc04` (source: seed, quality: 1.00)

- Entities: 6 | Coded: 6 | T1: 3 T2: 0 T3: 3 | Surface gaps: 0 | Written: yes

### `484b053ba7715477005dd3e3acd23461` (source: seed, quality: 0.75)

- Entities: 4 | Coded: 4 | T1: 3 T2: 0 T3: 1 | Surface gaps: 0 | Written: yes

### `d65d99b22adddf6294e45382bb67e3bf` (source: seed, quality: 0.40)

- Entities: 5 | Coded: 5 | T1: 3 T2: 0 T3: 2 | Surface gaps: 0 | Written: yes

### `1684fc9cac9cdffca7f2562713cadfad` (source: seed, quality: 0.50)

- Entities: 3 | Coded: 3 | T1: 3 T2: 0 T3: 0 | Surface gaps: 0 | Written: yes

### `57b79528bffbe7c945864780f0efb1c8` (source: seed, quality: 0.83)

- Entities: 5 | Coded: 5 | T1: 3 T2: 1 T3: 1 | Surface gaps: 0 | Written: yes

### `738f83295edf650359f8899eda67a512` (source: seed, quality: 1.00)

- Entities: 2 | Coded: 2 | T1: 2 T2: 0 T3: 0 | Surface gaps: 0 | Written: yes

### `e7f07b19b092668e5db74afeaedd58de` (source: seed, quality: 0.29)

- Entities: 5 | Coded: 5 | T1: 5 T2: 0 T3: 0 | Surface gaps: 0 | Written: yes

### `b0d44e28d9f858790925516733fa7d00` (source: seed, quality: 0.60)

- Entities: 5 | Coded: 5 | T1: 3 T2: 0 T3: 2 | Surface gaps: 0 | Written: yes

### `5ecd02417b2a3aebae72abd02dd418ac` (source: seed, quality: 0.43)

- Entities: 7 | Coded: 7 | T1: 4 T2: 1 T3: 2 | Surface gaps: 0 | Written: yes

### `5cef5638553da38ba0067a095be7d687` (source: seed, quality: 0.75)

- Entities: 7 | Coded: 7 | T1: 5 T2: 0 T3: 2 | Surface gaps: 0 | Written: yes

### `55e2f2d03b45fceda87b3e20874d9f4c` (source: seed, quality: 0.50)

- Entities: 6 | Coded: 6 | T1: 3 T2: 0 T3: 3 | Surface gaps: 0 | Written: yes

### `a1bab5c771b4916e7aa17252f76c7f8a` (source: seed, quality: 1.00)

- Entities: 1 | Coded: 1 | T1: 1 T2: 0 T3: 0 | Surface gaps: 0 | Written: yes

### `527f600993bdb171da888c97efb52500` (source: seed, quality: 1.00)

- Entities: 1 | Coded: 1 | T1: 0 T2: 1 T3: 0 | Surface gaps: 0 | Written: yes

### `fca406dcafe3270f52acbd472f882da3` (source: seed, quality: 1.00)

- Entities: 2 | Coded: 2 | T1: 0 T2: 1 T3: 1 | Surface gaps: 0 | Written: yes

### `c42266cf7c7133b9c4897e9bf8e898c9` (source: seed, quality: 1.00)

- Entities: 1 | Coded: 1 | T1: 1 T2: 0 T3: 0 | Surface gaps: 0 | Written: yes

### `bf168233c3fff8c257a7008304a44dd0` (source: seed, quality: 1.00)

- Entities: 1 | Coded: 1 | T1: 0 T2: 1 T3: 0 | Surface gaps: 0 | Written: yes

### `d87cf663c4e97acedd2b9b62314f8efa` (source: seed, quality: 1.00)

- Entities: 2 | Coded: 2 | T1: 2 T2: 0 T3: 0 | Surface gaps: 0 | Written: yes

### `21308060049c6d67cf3b4092576bc831` (source: seed, quality: 0.00)

- Entities: 1 | Coded: 1 | T1: 0 T2: 0 T3: 1 | Surface gaps: 0 | Written: yes

### `626ceaf6a02faeac285690dbeb19cce8` (source: seed, quality: 1.00)

- Entities: 1 | Coded: 1 | T1: 1 T2: 0 T3: 0 | Surface gaps: 0 | Written: yes

### `c531f4183acc11bbe6ed084eca659ac3` (source: seed, quality: 1.00)

- Entities: 1 | Coded: 1 | T1: 0 T2: 0 T3: 1 | Surface gaps: 0 | Written: yes

### `4087a4d13dbf4a14906de99cff26a258` (source: seed, quality: 1.00)

- Entities: 1 | Coded: 1 | T1: 1 T2: 0 T3: 0 | Surface gaps: 0 | Written: yes

### `82d89f2a7c76bf973cc795db35b4d98e` (source: seed, quality: 1.00)

- Entities: 1 | Coded: 1 | T1: 0 T2: 0 T3: 1 | Surface gaps: 0 | Written: yes

### `aabf30e1cab64f1e0255d2727f377e28` (source: seed, quality: 0.50)

- Entities: 1 | Coded: 1 | T1: 1 T2: 0 T3: 0 | Surface gaps: 0 | Written: yes

### `b1441cacde6721b1d95042562937b9ac` (source: seed, quality: 1.00)

- Entities: 1 | Coded: 1 | T1: 1 T2: 0 T3: 0 | Surface gaps: 0 | Written: yes

### `b51f7eac0a024ee793b5e97a84d10fe9` (source: seed, quality: 1.00)

- Entities: 1 | Coded: 1 | T1: 1 T2: 0 T3: 0 | Surface gaps: 0 | Written: yes


---

*Report generated by `scripts/evaluate_training_data.py` — 12656 TrainingLabel nodes updated.*
