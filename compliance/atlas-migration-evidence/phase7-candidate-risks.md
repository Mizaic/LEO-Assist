# Phase 7 - Candidate Risks (pattern sweep)

Risk-relevant code patterns detected in uncovered files. Each row is compared against the existing Atlas risk corpus (159 risks at the baseline snapshot). Hits with similarity >= 0.75 are pre-flagged as skip-already-covered; the rest are candidate-create and will be re-probed against live Atlas in Phase 8 before any creation.

| Pattern | Hits | Skip (>=0.75) | Candidate-create |
|---|---|---|---|
| `missing_org_scope` | 227 | 0 | 227 |
| `raw_llm_passthrough` | 1 | 0 | 1 |
| `raw_phi_logging` | 10 | 0 | 10 |
| **TOTAL** | **238** | **0** | **238** |

## Top candidate-create hits per pattern (max 25 each)

### `missing_org_scope` -- Cypher MATCH on Patient without org_id filter on same line

- `libs/classifiers/encounter_classifier.py:207` (best Atlas: R-CEB4789A score 0.327)
  - `"MATCH (p:Patient) WHERE toString(p.id) = $pid "`
- `libs/classifiers/encounter_classifier.py:262` (best Atlas: R-CEB4789A score 0.327)
  - `"MATCH (p:Patient) "`
- `libs/classifiers/encounter_classifier.py:282` (best Atlas: R-CEB4789A score 0.327)
  - `"MATCH (p:Patient) "`
- `libs/cypher/classification_vote_queries.py:13` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)`
- `libs/cypher/classification_vote_queries.py:35` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)`
- `libs/cypher/classification_vote_queries.py:90` (best Atlas: R-CEB4789A score 0.327)
  - `OPTIONAL MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e)`
- `libs/cypher/cleanup_queries.py:40` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->()`
- `libs/cypher/cleanup_queries.py:49` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[r:HAS_FINDING|HAS_DISORDER|HAS_SITUATION|HAS_OBSERVABLE|HAS_PROCEDURE|HAS_CONCEPT]->()`
- `libs/cypher/cleanup_queries.py:58` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)--(u:LLMUsage)`
- `libs/cypher/cleanup_queries.py:67` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)`
- `libs/cypher/cleanup_queries.py:80` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)`
- `libs/cypher/cleanup_queries.py:88` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_SAFETY_NET_ALERT]->(a:SafetyNetAlert)`
- `libs/cypher/cleanup_queries.py:102` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)`
- `libs/cypher/cleanup_queries.py:116` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_CSS_ALERT]->(a:CSSAlert)`
- `libs/cypher/cleanup_queries.py:130` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_EPISODE]->(ep:CancerEpisode)`
- `libs/cypher/cleanup_queries.py:144` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->()`
- `libs/cypher/cleanup_queries.py:153` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:IS_PART_OF]->(:EpisodeOfCare)`
- `libs/cypher/cleanup_queries.py:162` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(s)`
- `libs/cypher/cleanup_queries.py:169` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)`
- `libs/cypher/cleanup_queries.py:220` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)`
- `libs/cypher/synthetic_candidate_queries.py:94` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)`
- `scripts/_count_care_obstruction.py:37` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)`
- `scripts/_count_care_obstruction.py:44` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)`
- `scripts/_count_care_obstruction.py:55` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)`
- `scripts/_count_confirmed_cancer_2025.py:22` (best Atlas: R-CEB4789A score 0.327)
  - `MATCH (p:Patient)-[:HAS_EPISODE]->(ep:EpisodeOfCare)`
- _... 202 more hits omitted_

### `raw_llm_passthrough` -- Raw LLM output written back without HITL gate

- `scripts/review_anchor_training.py:189` (best Atlas: R-D8230A9A score 0.271)
  - `return response.text`

### `raw_phi_logging` -- Patient identifier or clinical text appears inside a logger call - potential PHI leak via application logs

- `libs/classifiers/encounter_textcat.py:81` (best Atlas: R-E1546339 score 0.395)
  - `logger.debug("EncounterTextcat: loaded rules from %s", path)`
- `scripts/analyse_referral_episodes.py:549` (best Atlas: R-E1546339 score 0.395)
  - `logger.info("Found %d patients", len(patient_ids))`
- `scripts/clean_patients.py:105` (best Atlas: R-E1546339 score 0.395)
  - `logger.info("Cleaning %d patients", len(patient_ids))`
- `scripts/explore_cancer_expressions.py:483` (best Atlas: R-E1546339 score 0.395)
  - `logger.info("Scanning encounters for %d patients...", len(patient_ids))`
- `scripts/run_gold_patients.py:163` (best Atlas: R-E1546339 score 0.395)
  - `logger.info("  Patient %s: %d total encounters", patient_id, len(encounters))`
- `scripts/run_gold_patients.py:281` (best Atlas: R-E1546339 score 0.395)
  - `logger.warning("  Patient %s sync: %s", patient_id, result["error"])`
- `scripts/run_gold_patients.py:338` (best Atlas: R-E1546339 score 0.395)
  - `logger.info("  Patient %s analysis complete", patient_id)`
- `scripts/validate_gold_5.py:144` (best Atlas: R-E1546339 score 0.395)
  - `logger.info("Validating %d patients: %s", len(patient_ids), patient_ids)`
- `scripts/validate_gold_5.py:154` (best Atlas: R-E1546339 score 0.395)
  - `logger.info("=== Patient %s ===", patient_id)`
- `services/analysis_worker/app/analyzers/episode_builder/_first_presentation.py:239` (best Atlas: R-E1546339 score 0.395)
  - `logger.warning("Referral context text query failed for patient %s", patient_id)`

