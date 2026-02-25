# NLP Training and Inference Pipeline — Verification and Validation Procedures

| Field            | Value                                    |
| ---------------- | ---------------------------------------- |
| Document ID      | NLP-PIPELINE-VV-001                      |
| Version          | 2.0.0                                   |
| Status           | Draft                                   |
| Date             | 2026-02-25                              |

---

## 1. Scope

This document defines verification and validation (V&V) procedures for:

1. **Training pipeline** (LLM) — correctness, robustness, integration
2. **Sync, Reset, and Writeback** — data integrity
3. **MedSpaCy runtime** — dry run validation vs gold
4. **End-to-end user journey** — happy path

---

## 2. Verification vs Validation

| Term | Definition | Example |
| ---- | ---------- | ------- |
| **Verification** | Build it right (meets design) | Unit tests, integration tests |
| **Validation** | Build the right thing (meets user need) | Dry run vs gold, user acceptance |

---

## 3. Unit Verification

### 3.1 Training Pipeline Components

| Component | Test | Pass Criteria |
| --------- | ---- | ------------- |
| Deidentify | PHI patterns replaced | No email, phone, NHS, postcode, name patterns in output |
| SentenceSplitter | Split on boundaries | No sentence spans overlap; coverage = input length |
| CodingResolver | Term -> Concept (hybrid) | Known term returns non-empty candidates via exact, fulltext, or vector search |
| CodingResolver | SurfaceForm boost | SurfaceForm match scored higher than equivalent Term match |
| CodingDisambiguator | Single candidate | Returns that candidate unchanged |
| Validator | Schema, context | Valid payload passes; invalid fails with expected reason |
| LLMUsage | Arithmetic | Usage + Usage sums correctly; cost calculation matches rates |

### 3.2 Reset Service

| Test | Pass Criteria |
| ---- | -------------- |
| Reset patient with DOCUMENTS | DOCUMENTS removed; Patient, Encounter, text remain |
| Reset patient with no DOCUMENTS | No error; 0 links_deleted |
| Reset non-existent patient | 404 or 0 links_deleted |

### 3.3 Reset Review Queue

| Test | Pass Criteria |
| ---- | -------------- |
| Reset review queue for patient | EncounterCandidates, ReviewTasks, Approvals, Changes removed |
| Reset review queue with no candidates | No error; 0 deleted |

### 3.4 Sync Service

| Test | Pass Criteria |
| ---- | -------------- |
| Sync with approved gold | DOCUMENTS created with correct evidence, concept_id |
| Sync with no approved gold | 400 error; 0 encounters_synced |
| Sync overwrites existing DOCUMENTS | Old DOCUMENTS removed; new match gold |

### 3.5 Terminology Writeback

| Test | Pass Criteria |
| ---- | -------------- |
| Writeback with approved candidates | SurfaceForm nodes created in Coding graph with MAPS_TO |
| Writeback normalisation | Surface forms normalised consistently (lowercase, punctuation stripped) |
| Writeback deduplication | Same (normalized, concept_id) pair not written twice |
| Writeback with no approved candidates | 0 surface_forms_written |
| Writeback skips terms without concept_id | Counted in skipped_no_concept |

### 3.6 Inference Service

| Test | Pass Criteria |
| ---- | -------------- |
| Infer with no model | Returns empty entities + guidance message |
| Infer with model | Returns entities with spans and labels |

---

## 4. Integration Verification

### 4.1 Training Pipeline End-to-End

| Test | Steps | Pass Criteria |
| ---- | ----- | ------------- |
| Run on 1 patient | POST /pipeline/run, 1 encounter | EncounterCandidate in Patient graph; ReviewTask created |
| Run dry_run | dry_run=true | No persistence; stats returned |
| Run with hard_fail | Encounter that fails validation | Candidate persisted; no ReviewTask; rejected_hard_fail incremented |
| Run multi-encounter | 5 encounters | 5 candidates; 5 tasks (or fewer if hard_fail) |
| LLM usage tracked | Run pipeline | llm_usage_json populated on EncounterCandidate |

### 4.2 Data Governance (Graph Separation)

| Test | Steps | Pass Criteria |
| ---- | ----- | ------------- |
| Pipeline does not write to Coding graph | Run pipeline, inspect Coding graph | No EncounterCandidate, ReviewTask, or patient_id in Coding graph |
| Review does not write to Coding graph | Approve task, inspect Coding graph | No Approval or Change nodes in Coding graph |
| Writeback writes only SurfaceForm | Trigger writeback | Only SurfaceForm + MAPS_TO in Coding graph; no patient data |

### 4.3 Reset -> Run -> Review -> Sync -> Writeback

| Test | Steps | Pass Criteria |
| ---- | ----- | ------------- |
| Full happy path | Reset -> Run -> Approve -> Sync | Patient DOCUMENTS match gold; SurfaceForm in Coding graph |
| Reset clears before run | Create DOCUMENTS -> Reset -> Run | Old DOCUMENTS gone; new run produces tasks only |
| Sync idempotent | Sync twice | Second sync produces same DOCUMENTS |
| Writeback idempotent | Writeback twice | SurfaceForm MERGE is idempotent; no duplicates |

---

## 5. Dry Run Validation (MedSpaCy vs Gold)

### 5.1 Purpose

After HITL for a patient, run MedSpaCy on the same encounter text and compare output to gold. Measures MedSpaCy quality before deployment.

### 5.2 Procedure

1. **Prerequisite**: Patient has approved gold in Patient graph (HITL complete).
2. **Input**: Patient ID.
3. **Process**:
   - Fetch encounter text from Patient graph.
   - Fetch gold from Patient graph (approved EncounterCandidate).
   - Run MedSpaCy on encounter text (no writes).
   - Align MedSpaCy output to gold (span overlap, concept match).
4. **Output**: Precision, recall, F1 per entity type; aggregate.

### 5.3 Alignment Rules

| Scenario | Match? |
| -------- | ------ |
| Gold span [10,20] "diabetes", MedSpaCy span [10,20] "diabetes", same concept | Yes |
| Gold span [10,20], MedSpaCy span [12,22] (overlap > 0.5) | Partial — configurable |
| Gold concept 73211009, MedSpaCy 73211009 | Yes |
| Gold concept 73211009, MedSpaCy 22298006 (different) | No |
| Gold has entity, MedSpaCy misses | False negative |
| MedSpaCy has entity, gold doesn't | False positive |

### 5.4 Metrics

- **Entity-level**: Precision = TP/(TP+FP), Recall = TP/(TP+FN), F1 = 2*P*R/(P+R)
- **Concept-level**: Same, but require concept_id match
- **Per-encounter**: Micro-average across terms
- **Aggregate**: Macro-average across patients

### 5.5 Thresholds

| Metric | Target | Action if Below |
| ------ | ------ | --------------- |
| F1 (entity) | >= 0.90 | Do not enable MedSpaCy for new patients |
| F1 (concept) | >= 0.85 | Add more gold; retrain |
| Precision | >= 0.92 | Reduce false positives (tune rules/model) |
| Recall | >= 0.88 | Add missing patterns; retrain |

---

## 6. Runtime-First Validation (MedSpaCy vs LLM)

### 6.1 Purpose

For new patients, run MedSpaCy first, then LLM on a sample. Compare agreement. Informs "could we have skipped LLM?"

### 6.2 Procedure

1. **Input**: Patient ID(s).
2. **Process**:
   - Run MedSpaCy on encounter text.
   - Run LLM pipeline on same encounters.
   - Compare outputs (before HITL or after).
3. **Output**: Agreement rate (%), disagreement cases for review.

### 6.3 Agreement Definition

- Span overlap > 0.5 AND concept_id match -> agree
- Otherwise -> disagree

### 6.4 Use

- Sample 10% of new patients for LLM run.
- If MedSpaCy-LLM agreement > 95% on sample, consider increasing MedSpaCy usage.

---

## 7. Regression Verification

### 7.1 Gold Dataset

Maintain a fixed set of encounters with known gold (e.g. 20-50). Run after each pipeline change.

### 7.2 Regression Test

| Test | Pass Criteria |
| ---- | -------------- |
| Training pipeline on gold set | F1 vs baseline >= -0.02 (no >2% drop) |
| Sync on gold set | Output DOCUMENTS identical to expected |
| Reset on gold set | No side effects; DOCUMENTS cleared |
| Writeback on gold set | SurfaceForm count matches expected |

### 7.3 Baseline

- Record F1, precision, recall at first passing run.
- Store as `baseline_metrics.json`.
- CI fails if new run drops below baseline - tolerance.

---

## 8. User Acceptance Validation

### 8.1 Happy Path Script

| Step | Actor | Action | Expected |
| ---- | ----- | ------ | -------- |
| 1 | User | Enter patient ID, max encounters, workers | Form accepts input |
| 2 | User | Click Run | Progress shown; run completes; LLM usage displayed |
| 3 | User | Open review queue | Tasks listed |
| 4 | User | Review, approve/edit | Edits saved; status updated |
| 5 | User | Click Sync gold | DOCUMENTS appear in Patient graph; surface forms written |
| 6 | User | View encounter | Coded spans visible |
| 7 | User | Click Reset | DOCUMENTS cleared; text remains |
| 8 | User | Export MedSpaCy training | entities.jsonl and kb.jsonl exported |
| 9 | User | Run inference (dry run) | Entities displayed (if model trained) |

### 8.2 Edge Cases

| Case | Expected |
| ---- | -------- |
| Run on patient with no encounters | 0 processed; no error |
| Sync with no approved tasks | 400; "No approved gold" |
| Reset on patient with no DOCUMENTS | Success; 0 cleared |
| Approve then Sync | Gold applied + surface forms written |
| Reject then Sync | Rejected encounter not synced |
| Infer with no model | Guidance message returned |
| Writeback with no approved gold | 0 written; no error |

---

## 9. Test Data Requirements

### 9.1 Minimum Test Set

- 1 patient with 1 encounter (smoke)
- 1 patient with 5+ encounters (multi-encounter)
- 1 encounter with hard_fail (validation)
- 1 encounter with negation/uncertainty (context)
- 1 encounter with inline Read code (e.g. "C10..")

### 9.2 Gold Reference Set

- 20-50 encounters with human-verified gold
- Covers: common disorders, findings, procedures, negations
- Stored in Patient graph as approved EncounterCandidates

---

## 10. V&V Checklist (Pre-Release)

- [ ] All unit tests pass (58+)
- [ ] Integration tests pass (Run, Reset, Sync, Writeback)
- [ ] Data governance verified (no patient data in Coding graph)
- [ ] Happy path UAT complete
- [ ] Edge cases exercised
- [ ] Regression baseline established (if applicable)
- [ ] Dry run validation run (MedSpaCy, when available)
- [ ] Documentation updated

---

## 11. Continuous Verification

| Trigger | Action |
| ------- | ------ |
| PR / merge | Run unit + integration tests |
| Nightly | Run on gold set; compare to baseline |
| Pre-release | Full V&V checklist |

---

## 12. Traceability

| Requirement | Verification Method |
| ----------- | ------------------- |
| HITL data in Patient graph only | Integration test: no patient data in Coding graph |
| Reset clears DOCUMENTS | Unit test: ResetService |
| Reset review queue clears HITL nodes | Unit test: ResetReviewQueueService |
| Sync applies gold | Integration test: SyncService |
| Writeback creates SurfaceForm | Unit test: TerminologyWritebackService |
| MedSpaCy F1 >= 0.90 | Dry run validation procedure |
| LLM usage tracked | Integration test: llm_usage_json populated |
| User can complete happy path | UAT script |
