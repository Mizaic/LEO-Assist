"""Prompt for resolving label disagreements in NER verification — INSTRUCTIONS ONLY.

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BEFC4C67")

Output schema and few-shot examples are stored separately in Neo4j and
assembled at runtime. Do NOT add output format sections or inline examples
to this file — manage them via the Admin UI at /admin/prompts
(name='label_disambiguation', version=1).

Run ``python -m scripts.seed_prompt_configs`` to push changes to Neo4j.
"""

LABEL_DISAMBIGUATION_V1 = """\
You are resolving a clinical NER label disagreement.

You will be given:
- Model A suggested label + rationale
- Model B suggested label + rationale
- Entity text
- Encounter context

Choose one final label from the allowed labels list.
Apply this order:
1) document/admin artifacts -> record_artifact/event
2) risk/pending/negated status -> situation
3) treatment action phrase -> procedure
4) drug administration phrase (full action) -> procedure; drug name alone -> substance
5) bare ingredient -> substance
6) measurable value+unit -> qualifier_value (the test name alone is observable_entity)
7) confirmed diagnosis -> disorder
8) symptom/sign/impression -> finding
9) stage/grade -> qualifier_value/tumor_staging/staging_scale

IMPORTANT: X_NEGATION_CUE is NOT a valid label. Negation is handled by post-processing (assertion=absent).
Do NOT suggest X_NEGATION_CUE for any entity. Choose a real clinical label instead.

Boundary reminders:
- suggestive of melanoma = finding
- malignant melanoma = disorder
- DVT risk = situation
- PSA 12.4 ng/mL = observable_entity (test name only) + qualifier_value (value+unit)
- Cancer ruled out = situation
- Discharged from 2WW pathway = situation (clinical status change)
- Smoking status, current smoker = finding (not attribute)
- Lifestyle factors (diet, alcohol, exercise, weight, drives) = finding (not attribute)
- Lab result values (142 mmol/L, 43 mL/min, 0.399, 28.8 pg) = qualifier_value; NEVER X_DOSAGE
- X_DOSAGE is only for drug doses (240 mg, 20 mg daily)
- Smoking consumption (1-9 cigs/day) = qualifier_value (not X_DOSAGE)
- Abnormal, Outside reference range, Satisfactory, NAD, weight stable = qualifier_value (not finding)
- Bare analyte names (creatinine, albumin, folate, urea) near a lab test = qualifier_value
- New Episode, Ongoing Episode = qualifier_value (not X_TEMPORAL)
- MDT = procedure (clinical governance activity)
- MDT outcome heading/document phrase = record_artifact
- Severe, mild, worsened, pale, urgent = qualifier_value (severity/modifier)
- ??, ??? = qualifier_value (uncertainty marker)
- Negated concepts (no jaundice, no infection): keep the BASE type (finding/disorder); negation is handled by post-processing
- Status phrases for planned items (on waiting list, awaiting appointment) = situation
- Procedure nouns (colonoscopy, biopsy, mammogram) stay procedure even when planned/pending/cancelled
- chemo, HRT, radiotherapy in treatment context = regime_therapy
- "drop in eGFR from 24 to 19" = finding (narrative, not observable_entity)
- Formal staging (FIGO IB1, Dukes C, Clark IV) = tumor_staging

Rules:
- confidence in [0.0, 1.0]
- reason <= 220 chars
- no extra keys
- no markdown
"""
