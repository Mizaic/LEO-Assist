# Clinical Extraction Scenario Source Map

This map lists the data sources we can use to generate validation
scenarios for `UN-89E2AE36`, `VAL-87173594`, and `VT-29880CC8`.

Validation target:

- Input: clinician-authored Markdown referral documents.
- Pipeline: run extraction only.
- Intercept: collect extracted strings before coding starts.
- Gold standard: clinician-approved JSON expected strings.
- Pass rule: phrase-level F1 is at least 95%.
- V1 fixture status: 97 synthetic, de-identified Markdown cases are
  drafted for clinician approval. The expanded set includes cases
  grounded in referral template fields, NICE NG12 symptom/action rows,
  and terminology surface-form spot checks. Do not treat them as scored
  validation evidence until `review_status` is updated after clinical
  sign-off and a live extraction run is recorded.

This map deliberately keeps coding and valueset checks out of the
fact-extraction validation. Coding/valueset mapping is a later stage.

## 1. Scenario Input Sources

### Referral templates

Use these as format and field-layout references when clinicians create
Markdown referral documents. Do not use binary templates directly as
automated inputs for `VAL-87173594`; convert the relevant structure into
Markdown test cases.

Files:

- `templates/20230523_EoE_USC_Proforma_LOWER_GI_FINAL_V6_1.docx`
- `templates/20250319_EoE_USC_Proforma_UGI__002.docx`
- `templates/2025_EoE_CA_Prostate_USC_Referral_Form_V1.1_Final.pdf`
- `templates/2025_EoE_CA_Urology_USC_Referral_Form_V1.1_Final.pdf`
- `templates/2WW-Non-site-specific-SystmOne.docx`
- `NSS_Test_patient Jenna Biggs.docx` user-supplied example of noisy SystmOne NSS referral export, used only as a structure/noise pattern for synthetic cases.
- `templates/Brain-CNS-Cancer-Referral-Form-No-Merge-fields-V3-Feb-2026.docx`
- `templates/Breast-Cancer-Referral-FormS1-v3.5.docx`
- `templates/EoE_CA_Gynae_Referral_Form_Feb_25_.docx`
- `templates/EoE_Skin_USC_Proforma_Final_2024.docx`
- `templates/Final__-_EOE_Lung_USC_referral_form._21.05.25.docx`
- `templates/Haematological-Cancer-Referral-Form-S1s.docx`
- `templates/HeadAndNeckCancerReferralForm-V6.docx`
- `templates/LowerGI_Cancer-Referral-Form-V6.docx`
- `templates/LungCancerReferralFormS1_V3.0.docx`
- `templates/Sarcoma-Referral-Form_V3.0.docx`
- `templates/Skin-cancer-suspected-referral-form-Devon-v4.1.1-S1.dotm`
- `templates/USCP-Gynaecology-Referral-Form-V8.docx`
- `templates/Upper-GI-Cancers-Referral-Form-S1s.docx`
- `templates/UrologicalCancerReferralForm-V5.0.docx`
- `templates/V20250930_USC_referral.pdf`

Scenario formats to generate:

- Referral letter.
- Email-style referral request.
- Semi-structured GP note.
- Markdown rendering of site-specific referral forms.
- Incomplete referral form.
- Noisy referral text with abbreviations.

### NICE NG12 scenario fixtures

Use these as an existing scenario pattern and as a source of
symptom/pathway combinations.

Files:

- `tests/fixtures/ng12_scenarios/ng12_extraction_scenarios.json`
- `tests/fixtures/ng12_scenarios/ng12_guideline_scenarios.json`
- `tests/fixtures/ng12_scenarios/ng12_sbar_scenarios.json`
- `tests/fixtures/ng12_scenarios/WORKFLOW.md`
- `tests/fixtures/ng12_test_scenarios.json`
- `reports/nice_ng12_raw/ng12_full.json`
- `reports/nice_ng12_raw/chapter_recommendations-organised-by-site-of-cancer.json`
- `reports/nice_ng12_raw/chapter_recommended-actions-organised-by-symptom-and-findings-of-primary-care-investigations.json`

Useful existing shape:

```json
{
  "id": "NG12-EXT-002",
  "encounter_note": "47 year old patient with haemoptysis.",
  "expected_entities": [
    {
      "text": "haemoptysis",
      "lookup_term": "haemoptysis",
      "semantic_tag": "finding",
      "assertion": "present"
    }
  ],
  "surface_forms_in_graph": [
    {
      "form": "haemoptysis",
      "concept_id": "66857006",
      "concept_fsn": "Hemoptysis (finding)"
    }
  ]
}
```

For the new validation, keep only what is needed for extraction F1:

- `source_markdown`.
- `expected_strings`.
- Optional `must_not_extract` (see routing patterns below).
- Optional `notes_for_clinician_review`.

### Informational referral routing (`must_not_extract`)

Phrase-level validation targets clinical facts (symptoms, investigation
results, labs, named arranged tests). These routing phrases may appear
verbatim in referral templates but are documented as must-not-extract for
clinician review; post-processing drops them via
`libs/ner/referral_routing_guard.py`:

- `2WW referral submitted` / `2WW referral placed`
- `Urgent 2WW` / `2WW brain/CNS referral` / site pathway labels
- `refer this patient under` / `suspected cancer referral`
- `e-Referral` transport lines

FIT shorthand surface forms from the knowledge graph are tested as separate lower-GI cases, including `+FIT`, `FIT+`, `FIT pos`, `FIT positive`, `positive FIT`, `FIT posotive`, `FIT abnormal`, `FIT raised`, `FIT neg`, `-FIT`, `neg FIT`, `FIT-`, `FIT below threshold`, and `FIT declined`.

### Clinical extraction prompt rules

Use these to understand what the extractor should emit and where to
intercept.

Files:

- `libs/prompts/extraction_v1.py`
- `libs/prompts/extraction_output_schema.py`
- `prompts/cancer_cohort_annotation_v1.md`
- `libs/prompts/extraction_examples.py`
- `libs/prompts/extraction_check_v1.py`

Relevant extraction output field:

- `terms[].text` is the exact extracted surface string under test.
- `terms[].lookup_term` is useful context, but not the primary
  `VAL-87173594` acceptance measure.
- Coding, valuesets, and SNOMED concept matches are downstream.

## 2. Gold JSON Shape

One JSON file should hold the clinician-approved expected strings for
the fixed Markdown document set.

Proposed path:

- `tests/fixtures/clinical_extraction_scenarios/expected_strings.json`
- Current V1 path: `tests/fixtures/clinical_extraction_scenarios/expected_strings.json`

Proposed shape:

```json
{
  "schema_version": 1,
  "normalisation": {
    "casefold": true,
    "trim": true,
    "collapse_whitespace": true,
    "strip_terminal_punctuation": true
  },
  "cases": [
    {
      "case_id": "lower_gi_letter_001",
      "source_markdown": "tests/fixtures/clinical_extraction_scenarios/markdown/lower_gi_letter_001.md",
      "format": "referral_letter",
      "site": "lower_gi",
      "expected_strings": [
        "rectal bleeding",
        "change in bowel habit",
        "unintentional weight loss"
      ],
      "must_not_extract": [
        "family history of bowel cancer"
      ],
      "notes_for_clinician_review": "Synthetic case authored by clinician panel."
    }
  ]
}
```

V1 locked fields:

- `schema_version`: `1`.
- `traceability.user_need`: `UN-89E2AE36`.
- `traceability.validation_test`: `VAL-87173594`.
- `traceability.verification_test`: `VT-29880CC8`.
- `validation_scope`: `extraction_only_terms_text_before_coding`.
- `pass_threshold.overall_phrase_f1`: `0.95`.
- `review_status`: `draft_for_clinician_approval` until a clinician
  approves the Markdown text and expected strings.

The automated VT should compute:

- True positives: extracted strings that match `expected_strings`.
- False positives: extracted strings not in `expected_strings`.
- False negatives: expected strings not extracted.
- Precision: true positives / (true positives + false positives).
- Recall: true positives / (true positives + false negatives).
- F1: 2 * precision * recall / (precision + recall).

Pass threshold:

- Overall phrase-level F1 >= 0.95.

Recommended report shape:

```json
{
  "overall": {
    "precision": 0.97,
    "recall": 0.96,
    "f1": 0.965,
    "passed": true
  },
  "by_case": [
    {
      "case_id": "lower_gi_letter_001",
      "missed_strings": [],
      "extra_strings": ["bowel cancer"],
      "passed": true
    }
  ]
}
```

## 3. Coding And Surface-Form Sources

These sources should help clinicians choose realistic phrases and help
authors check whether a phrase exists in the terminology graph. They
should not be part of the `UN-89E2AE36` pass criterion.

### Local SNOMED / NCDA mappings

Use these to seed phrase ideas and site coverage:

- `configs/snomed/snomed_ncda_symptom_mappings.json`
- `configs/snomed/snomed_ncda_primary_care_investigations_mappings.json`
- `configs/snomed/snomed_ncda_physical_signs_mappings.json`
- `configs/snomed/snomed_ncda_cancer_types_mapping.json`
- `configs/snomed/snomed_ncda_fast_track_referrals_mapping.json`
- `configs/snomed/snomed_ncda_cancer_risk_factors_mapping.json`
- `configs/snomed/snomed_ncda_family_history_mapping.json`
- `configs/snomed/snomed_ncda_comorbidities_mappings.json`
- `configs/snomed/snomed_ncda_treatment_mapping.json`
- `configs/snomed/snomed_ncda_observable_entities_mapping.json`
- `configs/snomed/snomed_ncda_referral_outcomes_mapping.json`
- `configs/snomed/snomed_ncda_stage_of_diagnosis_mapping.json`
- `configs/snomed/snomed_ncda_screening_mapping.json`
- `configs/snomed/snomed_ncda_seen_by_specialist_mapping.json`
- `configs/snomed/snomed_ncda_place_of_first_presentation_mapping.json`
- `configs/snomed/snomed_ncda_lifestyle_factors_mapping.json`

Loader:

- `scripts/load_preapproved_surface_forms.py`

The loader extracts surface forms from `guideline_synonyms` and
`preferred_term` values in `snomed_ncda_*.json` files.

### Surface-form enrichment and audit sources

Use these as phrase banks and gap reports:

- `scripts/hitl_phase4_report.json` - 167 surface forms added, 113 reviews resolved.
- `scripts/remediate_hitl_phase4.py` - curated cancer, shorthand, and common clinical term groups.
- `reports/surface_form_dedup_audit.csv` - duplicate surface forms with multiple concept mappings.
- `scripts/investigations/surface_form_full_audit.py` - graph audit script and report path.
- `scripts/expand_surface_forms_llm.py` - LLM-assisted synonym expansion workflow.
- `scripts/dedup_surface_forms.py` - duplicate MAPS_TO remediation.

Known ambiguity source:

- `reports/surface_form_dedup_audit.csv` shows terms such as
  `screening`, `asthma`, `back pain`, `weight`, and investigations with
  multiple concept mappings. These are useful negative / ambiguity cases
  but should be curated carefully.

Template-review terminology spot checks on 2026-05-18 found:

- Strong surface-form coverage for `FIT`, `PSA`, `CA125`,
  `pleural effusion`, `Bence Jones protein detected`,
  `full blood count`, `haematuria`, `thrombocytosis`, and
  `chest X-ray`.
- `FIT` and `PSA` are multi-mapped and should be used in ambiguity or
  tag-filtering cases as well as positive cases.
- `spirometry`, `FEV1`, `Rockwood performance score`, and
  `MERGE FIELD` have useful behaviour for validation: some resolve via
  broader terminology search, but they do not have clean exact
  SurfaceForm coverage. Use them to stress extractor output and
  `must_not_extract` handling.

## 4. Knowledge Graph Inventory

Queried through `user-leo-neo4j` on 2026-05-18.

Available graph sources:

- `SurfaceForm`: 7,426 nodes by label count.
- `SurfaceForm` with `MAPS_TO`: 7,565 rows, mapped to 2,041 distinct concepts.
- `Concept`: 1,042,458 nodes.
- `Term`: 1,610,070 nodes.
- `ValueSet`: 31 nodes.
- `AppropriatenessRule`: 29 nodes.
- Cancer Audit domain: 20 subdomains found.

Surface form provenance counts:

- `ncda_preapproved`: 3,102.
- `gold_label_editor`: 1,606.
- `manual`: 1,307.
- `lab_coder_v1`: 1,045.
- `manual_curation`: 160.
- `stage_of_diagnosis_kg`: 103.
- `ncda_ethnicity_config`: 95.
- `manual_pin`: 80.
- `coding_review`: 46.
- `batch_coding_review`: 10.
- `lab_coder_fix_v1`: 4.
- `terminology_2ww_audit`: 2.

Cancer Audit subdomains available:

- `stage_of_diagnosis`
- `results_of_primary_care_investigations`
- `cancer_types`
- `fast_track_referrals`
- `treatment`
- `symptoms`
- `comorbidities`
- `physical_signs`
- `investigations`
- `lifestyle_factors`
- `family_history`
- `cancer_risk_factors`
- `place_of_presentation`
- `seen_by_specialist`
- `referral_outcomes`
- `screening`
- `observable_entities`
- `ethnicity`
- `housebound_status`
- `living_arrangement`

Useful graph lookup pattern:

1. Use `search_surface_forms(q=<phrase>, limit=...)`.
2. If there is no hit, try a shorter phrase.
3. Use `run_cypher_knowledge` only when no named tool covers the
   question.

Example graph hit:

- Query: `rectal bleeding`.
- Returned forms include:
  - `Rectal bleeding` to `405729008` / `Hematochezia (finding)`.
  - `RB - Rectal bleeding` to `12063002` / `Rectal hemorrhage (disorder)`.
  - `bright red rectal bleeding` to `405729008` / `Hematochezia (finding)`.

## 5. Scenario Generation Dimensions

Use these dimensions to build a balanced fixed validation set.

### Format

- `referral_letter`
- `email_request`
- `semi_structured_note`
- `referral_form_markdown`

### Cancer site / pathway

Seed from `templates/` and NG12 fixtures:

- lower GI
- upper GI
- lung
- breast
- urology
- prostate
- gynaecology
- skin
- head and neck
- brain / CNS
- haematology
- sarcoma
- non-site-specific

### Extraction phrase class

- symptom or finding
- physical sign
- investigation result
- procedure or referral
- family history
- risk factor
- comorbidity
- treatment
- cancer type / suspected cancer situation
- performance or staging scale

### Assertion / context

These are useful for future evidence, but `UN-89E2AE36` measures only
the extracted strings:

- present
- absent / refuted
- possible
- historical
- family history
- planned
- declined / cancelled

### Difficulty

- Simple sentence with one expected string.
- Dense paragraph with several strings.
- Abbreviation (`2WW`, `USC`, `LGI`, `CXR`, `FIT`, `PSA`).
- Repeated phrase with one relevant mention.
- Negative phrase that must not be extracted.
- Ambiguous phrase from the dedup audit.
- Lab/vitals row with values.
- Referral form checkbox or field label.

## 6. Recommended Folder Layout

```text
tests/fixtures/clinical_extraction_scenarios/
  SCENARIO_SOURCE_MAP.md
  SCENARIO_MATRIX.md
  expected_strings.json
  template_markdown/
    2ww_non_site_specific_systmone.md
    ...
  markdown/
    lower_gi_letter_001.md
    lower_gi_email_001.md
    lung_form_001.md
    breast_semistructured_001.md
  reports/
    latest_extraction_f1_report.json
```

## 7. Generation Rules

For each scenario:

1. Start from a real template or NG12 branch.
2. Convert the scenario into a de-identified Markdown document.
3. Ask clinicians to approve the final Markdown text.
4. Ask clinicians to approve the `expected_strings` list.
5. Include only strings that should be extracted before coding.
6. Put coding, SNOMED concept ids, valuesets, and cancer audit
   subdomains in optional metadata only.
7. Run the extraction pipeline.
8. Intercept `terms[].text` before coding.
9. Compare extracted strings to `expected_strings`.
10. Record missed strings and extra strings.

Template rendering rule:

- Each binary referral template has a Markdown rendering under
  `template_markdown/`.
- `.docx` and `.dotm` files are rendered from WordprocessingML.
- PDF files are represented by manual-transcription placeholders until
  a clinician copies out their visible headings and fields.
- Scenario Markdown should be written from these rendered templates
  rather than directly from the binary files.
- Every scenario in `expected_strings.json` must set
  `source_template_markdown` to a rendered template path and the
  scenario Markdown must include the rendered template path plus
  completed template fields.
- Every scenario must include a `synthetic_patient` object and a
  `## Synthetic Patient Details` section. Patient identifiers must be
  visibly fake, for example `Synthetic Given 001`, `SYN-NHS-000001`,
  and `example.invalid` practice emails.
- Every scenario must include a `blood_results` object sourced from
  `configs/reference_ranges/nhs_haematology_defaults.json` and a
  `## Blood Results (Last 2m)` Markdown section. Observable entities
  should be represented as the test name in `expected_strings`, with
  value and unit captured in `expected_observables`.

## 8. Open Gaps

- The V1 Markdown corpus exists as 80 synthetic draft cases, but still
  needs clinician approval before it can be used as scored validation
  evidence.
- The expected-string JSON exists with `review_status` set to
  `draft_for_clinician_approval`; clinician sign-off is still required.
- Normalisation rules are locked in `expected_strings.json`.
- NICE NG12 and referral templates have been used as source material,
  but clinician review must confirm each Markdown conversion is
  clinically realistic and de-identified.
- Referral form PDFs still need clinician-led copy-out into Markdown if
  PDF-only heading/layout details must be represented.
- `reports/latest_extraction_f1_report.json` is present with
  `status: not_run` until a live extraction-only run is executed.
