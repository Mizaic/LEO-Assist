---
name: Opus-in-the-Loop Auditor
overview: Design and implement an "Opus in the Loop" auditor that uses Claude Opus 4.6 (AWS_MAX_MODEL) to comprehensively review every TrainingLabel record — validating entities, assertions, values, SNOMED codes, and span boundaries — with a tiered autonomy model that auto-fixes safe issues and escalates risky ones for human approval.
todos:
  - id: opus-prompt
    content: Write the Opus audit system prompt (libs/prompts/opus_audit_v1.py) incorporating extraction rules, label verification ladder, tier thresholds, verdict schema, and safe-fix boundaries
    status: pending
  - id: auditor-script
    content: Build scripts/opus_training_auditor.py — fetch labels, call Opus via LLMClient factory, parse verdicts, apply auto-fixes (dry-run/apply), generate JSONL audit trail
    status: pending
  - id: report-gen
    content: Generate Markdown summary report after run — counts by verdict category, auto-fix breakdown, sample proposals for human review
    status: pending
  - id: schema-validation
    content: Add strict JSON schema validation for Opus response parsing with fallback/retry on malformed output
    status: pending
  - id: dry-run-test
    content: Run on a small batch (--limit 50) in dry-run mode to validate prompt quality and verdict distribution before full run
    status: pending
isProject: false
---

# Opus-in-the-Loop TrainingLabel Auditor

## What Opus Should Check

For each TrainingLabel, Opus receives the **encounter text** and the full **entities_json** array. It performs a multi-dimensional audit:

### 1. Entity Completeness

- **Missing entities:** Are there clinically significant concepts in the encounter text that were not extracted?
- **Spurious entities:** Were non-clinical tokens (admin, section headings, safety-netting advice) incorrectly extracted?
- **Over-capture:** Is the `text` span too wide (e.g. includes Read codes, reference ranges, result values that should not be in the entity text)?

### 2. Semantic Tag (Label) Correctness

- Does the `label` match the SNOMED semantic tag conventions? (e.g. drug = `substance`, not `procedure`; lab test = `observable entity`, not `finding`; planned procedure = `situation`, not `procedure`)
- Apply the same decision ladder from `label_verification_v2.py`

### 3. Assertion Correctness

- Is the assertion (`present`, `absent`, `historical`, `possible`, `family`, `hypothetical`, `refuted`, `declined`) correct given the **full sentence context**?
- Negation scope: does a leading "No" / "Nil" / "Denies" correctly cascade to all entities in that sentence?
- Historical cues: "resolved", "previous", past-tense language, PMH sections
- Hedging cues: "?", "query", "suspected", "possible"

### 4. Value / Unit / Reference Range (Observable Entities)

- For `observable entity` labels: are `value`, `unit`, and `reference_range` correctly populated?
- Are they correctly **absent** for non-observable entities?
- Does the value match what's in the source text?

### 5. SNOMED Coding Quality

- Does `snomed_term` semantically match the extracted `text` / `normalized` term?
- Is the concept too broad (e.g. "Clinical finding" when a specific concept exists)?
- Is the semantic tag of the SNOMED concept consistent with the entity label?
- Does `decision_tier` make sense given the `snomed_score`?

### 6. Span Boundary Accuracy

- Does `text` correspond to a real substring of the encounter?
- Are `start` and `end` offsets correct?
- Is the `normalized` form a reasonable clinical normalisation of `text`?

## Opus Verdict Schema

For each entity, Opus returns:

```json
{
  "entity_index": 0,
  "verdict": "correct | fixable | needs_review | remove",
  "issues": [
    {
      "field": "assertion",
      "current": "present",
      "suggested": "absent",
      "confidence": 0.97,
      "rationale": "Sentence opens with 'No' — negation scope covers this entity"
    }
  ],
  "missing_entities": [
    {
      "text": "chest pain",
      "label": "finding",
      "assertion": "absent",
      "confidence": 0.92,
      "rationale": "Negated finding not extracted"
    }
  ]
}
```

## Autonomy Tiers


| Verdict                                                    | Opus Action              | Human Action             |
| ---------------------------------------------------------- | ------------------------ | ------------------------ |
| `correct`                                                  | No change                | None                     |
| `fixable` (confidence >= 0.95 AND field in safe-fix set)   | **Auto-apply** and log   | Review in batch report   |
| `fixable` (confidence < 0.95 OR field not in safe-fix set) | **Propose** only         | Approve/reject in report |
| `needs_review`                                             | Flag with rationale      | Must review              |
| `remove`                                                   | **Propose** removal only | Must approve             |


### Safe Auto-Fix Fields

These are fields Opus can correct autonomously when confidence >= 0.95:

- `text` span boundaries (over-capture trimming, like the fix we just did)
- `assertion` when the correction follows deterministic rules (negation scope, "resolved" -> historical)
- `value`, `unit`, `reference_range` when correcting to match source text exactly
- `label` when the correction aligns with the SNOMED concept's semantic tag

### Requires Human Approval

- Removing an entity entirely
- Changing `snomed_concept_id` or `snomed_term`
- Adding a new entity that was missing
- Any fix where Opus confidence < 0.95
- Changing `assertion` in ambiguous cases (e.g. "improving" = present vs historical)

## Tools / Knowledge Opus Needs

### Provided in the System Prompt

- The full extraction rules from [extraction_v1.py](libs/prompts/extraction_v1.py) (semantic tags, assertion rules, surface form rules, evidence-concept alignment, intended use boundaries)
- The label verification decision ladder from [label_verification_v2.py](libs/prompts/label_verification_v2.py)
- The tier classification thresholds from [tier_classifier.py](libs/coding_engine/tier_classifier.py) (T1 >= 0.95, T2 >= 0.70)
- Explicit instructions on the safe-fix vs needs-approval boundary

### Provided per Record (User Message)

- Full encounter text
- `entities_json` array with all fields
- Record metadata: `source`, `quality_score`, `label_id`

### NOT Provided (Safety Boundary)

- Opus does **not** query Neo4j or the terminology API — it cannot look up SNOMED codes itself
- Opus does **not** see other patient records
- Opus cannot modify Neo4j directly — all writes go through the script's write layer

## Safety Design

### What We CAN Assess

- **Extraction quality:** Opus can judge whether `text` spans, assertions, labels, and values are correct by reading the encounter text — this is a text-comprehension task it excels at
- **SNOMED plausibility:** Opus can judge whether a given `snomed_term` semantically matches the entity (e.g. "hypertension" mapped to "Essential hypertension" = plausible; "sore throat" mapped to "Dysuria" = implausible)
- **Internal consistency:** assertion vs tier, label vs semantic tag, value vs source text

### What We CANNOT Assess (and Should Not Try)

- **Whether the encounter text itself is correct** — the source data may have been entered incorrectly by the GP; Opus audits the *coding*, not the *clinical record*
- **Whether the old pipeline's decisions were appropriate at the time** — we're evaluating the current state, not retroactively judging
- **SNOMED concept specificity** without terminology lookup — Opus can flag "this seems too broad" but cannot verify the concept hierarchy
- **Patient safety impact** — this is a training data audit, not a clinical decision. The TrainingLabels are used to train/evaluate an NER model, not to make treatment decisions

### Guard Rails

1. **Prompt injection defence:** Use existing `INJECTION_GUARD` + `sanitise_for_prompt()` from [prompt_safety.py](libs/llm_client/prompt_safety.py) for encounter text
2. **Output validation:** Parse Opus JSON response with strict schema validation; reject malformed output
3. **Auto-fix cap:** If Opus proposes auto-fixes on > 30% of entities in a **sliding window of 100 records**, pause and alert — this catches systemic issues early rather than waiting until the end of a full 12,600-record run
4. **Audit trail:** Every auto-fix and every proposal is logged to a JSONL file with `label_id`, `entity_index`, `field`, `old_value`, `new_value`, `confidence`, `rationale`
5. **Dry-run default:** Script runs in `--dry-run` mode by default; `--apply` flag required to write
6. **Batch reporting:** After the run, generate a Markdown report summarising: records reviewed, auto-fixed, proposed, flagged, and a sample of each category
7. **Entity format normalisation:** `entities_json` has two formats in the wild — flat fields (`snomed_concept_id`, `snomed_score` at root) and nested (`coding.snomed_concept_id`, `coding.score`). The script must normalise to the flat format on read (matching what `evaluate_training_data.py` produces) and write back in flat format
8. **Token budget:** The system prompt (extraction rules + label ladder + tier thresholds + audit instructions) will be large (~4-5K tokens). Combined with per-record input (~1-2K), the total fits well within Opus's 200K context window, but prompt caching is critical for cost — structure the system prompt as a stable prefix so Bedrock caches it across calls

## How to Run It

### Phase 1: Script (recommended for initial deployment)

A Python script `scripts/opus_training_auditor.py` that:

1. Fetches all included TrainingLabels from Neo4j (custom query returning `text` + `entities_json` + metadata — not the evaluate_training_data query, which omits `entities_json`)
2. Sends each to Opus via the existing `LLMClient` factory (`create_llm("aws", "max")`)
3. Parses structured JSON verdicts
4. Applies auto-fixes in dry-run or write mode
5. Generates a Markdown report + JSONL audit trail

Concurrency: `ThreadPoolExecutor(max_workers=5)` — Opus has lower Bedrock throughput limits than Haiku/Sonnet. Configurable via `OPUS_AUDIT_WORKERS` env var. The script must handle `ThrottlingException` with exponential backoff (start 2s, max 60s, jitter).

Cost estimate: ~12,600 records. System prompt (extraction rules + label ladder + tier thresholds + audit instructions) is ~4-5K tokens, cached after first call. Per-record variable input ~1-2K tokens, output ~500 tokens. At Opus pricing (~$15/M input, ~$75/M output):

- Input (variable): 12,600 x ~1.5K = ~19M tokens -> ~$285
- Output: 12,600 x ~500 = ~6.3M tokens -> ~$470
- System prompt (cached, reduced cost): ~$15-30
- **Estimated total: $400-800 for a full run**
- Recommend batched runs (e.g. 500 records via `--limit` / `--offset`) to validate before committing to full cost

### Phase 2 (future): API + UX

- Expose via an `/audit/review` endpoint that serves proposed fixes for human approval
- Simple web UI showing encounter text, current entities, and Opus proposals with accept/reject buttons
- But Phase 1 (script + Markdown report) is the right starting point — get the prompt right before building UI

## Implementation Structure

```
scripts/opus_training_auditor.py        # main script
libs/prompts/opus_audit_v1.py           # system prompt — register("opus_audit", version=1, text=...)
```

The prompt module follows the existing registry pattern: define a `OPUS_AUDIT_SYSTEM_V1` constant, call `register("opus_audit", version=1, text=OPUS_AUDIT_SYSTEM_V1)` at module load. Retrieve via `get_prompt("opus_audit", version=1)`.

The script reuses:

- `libs/llm_client/factory.py` — `create_llm("aws", "max")` for Opus
- `libs/llm_client/prompt_safety.py` — `INJECTION_GUARD`, `sanitise_for_prompt()`
- `libs/neo4j_client/client.py` — `PatientGraphClient` for reads/writes
- `libs/cypher/training_label_queries.py` — existing fetch/update queries

## Key Architectural Decisions

1. **Opus only, no consensus:** For this audit task we use Opus alone (not dual-model consensus). Consensus is for extraction where speed matters and we use cheaper models. For auditing, we want the best model's full reasoning. If Opus is uncertain, it flags for human review rather than calling a second model.
2. **Read-only by default:** The script defaults to `--dry-run`. Auto-fixes are only written with `--apply`, and even then, only for the safe-fix categories above.
3. **Stateless per record:** Each record is evaluated independently. Opus does not carry context between records (no cross-record bias).
4. **Incremental runs:** Track `audited_at` timestamp on TrainingLabel nodes so the script can skip already-audited records on re-run (`--skip-audited` flag). `audited_at` is written **per-record immediately** after Opus returns its verdict (even in dry-run mode, to mark "reviewed, no changes needed"), so a crash mid-run allows seamless resume without re-processing.

