# Cancer Audit -- Learning Log

Each row captures one clinical signal found during encounter reading.
The goal is to turn every gap into a concrete improvement.

| # | Patient ID | Encounter date | Signal in text | Was it coded? | In concept set? | Pipeline used it? | Gap type | Improvement action | Status |
|---|-----------|---------------|----------------|--------------|----------------|-------------------|----------|--------------------|--------|
| 1 | 4742236882 | 2025-02-26 | Acute abdomen -> ED referral for right flank pain, hypercalcaemia found on admission | Yes (coded by hospital as metastasis to bone unknown primary) | Yes (CANCER_TYPE_IDS) | Yes -- episode built | None -- pathway correctly captured | None needed | Done |
| 2 | 4742236882 | 2025-03-24 | Infiltrating duct carcinoma confirmed via biopsy letter | Yes (coded by GP from letter) | Yes | Yes | None | None needed | Done |
| 3 | 4587069337 | 2022-06-08 | Malignant tumor of breast on problem list | Yes | Yes | Yes -- but may be historical | HISTORY_PRESENT flag needed; breast screening normal May 2024 contradicts active cancer | Add HISTORY_PRESENT logic to episode classifier; set needs_review | Pending |
| 4 | 4587069337 | 2024-05-09 | Breast neoplasm screening normal (NHS BSP letter) | Yes (coded as BCSP normal) | Partial -- in CANCER_EXCLUSION_IDS as weak exclusion | Not used to disambiguate history vs active | Pipeline does not cross-reference BSP normal result against active cancer code | Add rule: if BSP_NORMAL present AND cancer code has no treatment follow-up -> flag HISTORY_PRESENT | Pending |
| 5 | 7306752529 | 2024-03-07 | Fast track referral for suspected head and neck cancer (EMIS XaMkD) | Yes in EMIS, No in Neo4j DOCUMENTS | Yes (280521000000108 confirmed via terminology server) | No -- SNOMED not linked in graph | CONCEPT_MISSING (ingestion gap) | Map XaMkD -> 280521000000108 in ingestion pipeline; fix_7306752529.py corrected to use 280521000000108 | Pending |
| 6 | 7306752529 | 2024-06-12 | Encapsulated poorly differentiated thyroid carcinoma (secondary care letter) | Yes (GP coded on problem list) | Note: 363432004 = trachea not thyroid (verified 2026-04-03) -- actual thyroid code needed | Yes -- but episode was no_referral due to row 5 gap | PIPELINE_LOGIC_ERROR (cascades from row 5) | Fix via fix_7306752529.py (SNOMED corrected to 280521000000108 for referral) | Pending |
| 7 | 4562218347 | 2024-05-31 | Invasive ductal carcinoma right breast via breast clinic letter | Yes (GP coded from letter) | Yes | Yes | SPECIALIST_VISIT_MISSED -- no 2WW because screening-detected | Add SCREENING_DETECTED pathway category to episode builder; do not flag as no_referral | Pending |
| 8 | 4562218347 | 2024-06-18 | Wide local excision + sentinel node biopsy + mammoplasty | Yes (coded) | Partial -- lumpectomy in TREATMENT_IDS but not sentinel node biopsy | Partial | TREATMENT_MISSED (sentinel node) | Add sentinel node biopsy SNOMED to TREATMENT_IDS | Pending |
| 9 | 4563706582 | 2024-12-02 | IDA + weight loss + anorexia in older male -- GP sent direct access endoscopy referral | Partial (IDA coded) | N/A -- not a SNOMED gap | No -- endoscopy referral not a 2WW code | REFERRAL_MISSED (NICE NG12 criteria met but GP used direct access rather than 2WW) | Add NLP signal for direct-access endoscopy referral as soft indicator of upper GI pathway | Pending |
| 10 | 4563706582 | 2025-01-14 | Carcinoma of stomach and junctional oesophagus confirmed at endoscopy biopsy | Yes | Partial -- cid=255080008 labelled "Carcinoma of stomach" in Neo4j but SNOMED 255080008 is "Malignant neoplasm of urinary bladder" | No -- concept name/ID mismatch in KG | CONCEPT_NOT_IN_SET (KG mapping error) | Audit EMIS->SNOMED mappings for gastric/oesophageal codes; fix X78gA mapping | Pending |
| 11 | 4992507875 | 2024-10-15 | Pigmented dermatofibrosarcoma protuberans (EMIS X77oW) on left thigh | Yes (GP coded from specialist letter?) | No -- cid=372130007 in Neo4j is "haematopoietic" not skin/sarcoma | No -- wrong concept ID in KG | CONCEPT_NOT_IN_SET (KG mapping error: DFSP mapped to haematopoietic concept) | Find correct SNOMED for DFSP (likely 40012004 or descendant); fix graph mapping | Pending |
| 12 | 4992507875 | 2024-10-15 | Lump L thigh increasing in size over 4/52 -- no 2WW sarcoma referral visible | Unclear | N/A | No | REFERRAL_MISSED (sarcoma 2WW not coded or not sent via 2WW route) | Add sarcoma as a high-priority flag in no-referral review; no-referral sarcomas need MDT confirmation | Pending |
| 13 | 4202301609 | 2025-09-13 | Lymphoma team consulted (internal, secondary care) after CT renal lesion | No (internal consult, not coded in primary care) | N/A | No | SPECIALIST_VISIT_MISSED (secondary care internal referral, not visible in GP record) | Note: not a gap we can detect from primary care records alone -- needs secondary care data | Pending |
| 14 | 4202301609 | 2025-11-13 | CT-guided retroperitoneal biopsy | Yes (coded) | Partial -- biopsy (115959002) in TREATMENT_IDS | Not used -- patient was in lower_gi episode from colonoscopy pathway | PIPELINE_LOGIC_ERROR -- biopsy of a different site not linked to new cancer episode | Add logic: if biopsy of new site occurs >60 days after initial diagnosis, start new episode evaluation | Pending |

---

## Gap types (vocabulary)

| Gap type | Description |
|----------|-------------|
| `CONCEPT_MISSING` | Signal present in text, not coded, concept not in our set |
| `CONCEPT_NOT_IN_SET` | Signal coded with a SNOMED ID not in our concept set |
| `PIPELINE_LOGIC_ERROR` | Concept in set but pipeline rule didn't fire correctly |
| `ASSERTION_WRONG` | Concept coded but assertion (historical/present/absent) incorrect |
| `HISTORY_PRESENT` | Active-looking code is actually a historical problem-list entry |
| `WEAK_EXCL_OVERCAPTURE` | Weak exclusion code incorrectly cancelled an active diagnosis |
| `REFERRAL_MISSED` | Referral text present in encounter but not coded as fast-track |
| `TREATMENT_MISSED` | Treatment (chemo, radio, hormone) in text but not coded |
| `SPECIALIST_VISIT_MISSED` | Specialist clinic letter received but not coded as specialist visit |
| `NO_GAP` | Signal correctly captured, no improvement needed |

---

## Improvement actions tracker

| ID | Gap type | Description | Target file | Status |
|----|----------|-------------|-------------|--------|
| A1 | HISTORY_PRESENT | Add BSP normal result as signal to check against active cancer code | `scripts/remediate_episodes.py`, `libs/domains/ncda_concept_sets.py` | Planned |
| A2 | PIPELINE_LOGIC_ERROR | Add `HISTORY_PRESENT` flag to episode classifier when cancer code has no treatment follow-up and >18 months of no cancer activity | `services/analysis_worker/app/analyzers/episode_builder.py` | Planned |
| A3 | Concept set | Add `68620` (Breast neoplasm screening normal) to weak exclusion set with annotation "may indicate historical cancer" | `libs/domains/ncda_concept_sets.py` | Planned |
| A4 | UX | Surface `needs_review` episodes with HISTORY_PRESENT flag in operations review queue | `services/ui/src/components/operations/ReviewSection.tsx` | Planned |
| A5 | Agent prompt | Add context note to Ask LEO: "if a patient has a cancer code but no treatment, specialist visit, or secondary care letters within 12 months, the code may be historical" | `libs/llm_client/escalation.py` | Planned |
| A6 | New feature | Build no-referral cohort card and deep-dive agent (see INVESTIGATION_NOTES.md architecture) | Multiple files | Planned |
| A7 | EMIS ingestion | Map EMIS fast-track referral codes (XaMkD etc.) to correct SNOMEDs in ingestion pipeline. XaMkD = 280521000000108 (head+neck), confirmed via terminology server. Audit all 14 codes. | Ingestion pipeline | Planned |
| A8 | REFERRAL_SITE bug | REFERRAL_SITE in remediate_episodes.py was correct originally. My "fix" introduced errors by trusting wrong ncda_concept_sets.py comments. REVERTED to correct mapping. Re-run remediation. | `scripts/remediate_episodes.py` | Fixed, re-run needed |
| A9 | New pathway | Add SCREENING_DETECTED as a valid referral_site category in episode builder and dashboard | `scripts/remediate_episodes.py`, `services/ui` | Planned |
| A10 | KG mapping | EMIS code X78gA (carcinoma of stomach) mapped to SNOMED 255080008 (not in our KG). Stomach cancer code 363349007 added to CANCER_TYPE_IDS. | Knowledge graph ingestion | Partial |
| A11 | KG mapping | EMIS code X77oW (DFSP) mapped to SNOMED 372130007 which IS "Malignant neoplasm of skin" (correct). Comment in ncda_concept_sets.py was wrong (not the code). | `libs/domains/ncda_concept_sets.py` | Fixed (comment corrected) |
| A12 | Concept set | Add sarcoma pathway awareness: DFSP should trigger sarcoma 2WW flag, not skin | `libs/domains/ncda_concept_sets.py` | Planned |
| A13 | Data delete | Delete patient 6230411040 (outside audit window). Use safe_delete_patient.py | `scripts/investigations/safe_delete_patient.py` | Ready to apply |
| A14 | CRITICAL BUG | 385194003 ("Suppository, basic dose form") was in CANCER_SUSPECTED_IDS causing false-positive cancer flags. Removed. Correct code 162572001 "Malignant neoplastic disease suspected" added. | `libs/domains/ncda_concept_sets.py` | FIXED |
| A15 | Comment audit | All FAST_TRACK_REFERRAL_IDS, SEEN_BY_SPECIALIST_IDS, CANCER_TYPE_IDS comments were misaligned (alphabetical labels on numerical IDs). All corrected against terminology server. | `libs/domains/ncda_concept_sets.py` | FIXED |
| A16 | Missing codes | CANCER_TYPE_IDS was missing 363349007 (stomach cancer) and 363402007 (oesophageal cancer). Both added. | `libs/domains/ncda_concept_sets.py` | FIXED |
| A17 | KG not found | 255080008 and 269457002 not found in our knowledge graph. Removed from CANCER_TYPE_IDS. | `libs/domains/ncda_concept_sets.py` | FIXED |
| A18 | Thyroid cancer | 363432004 is "trachea" not "thyroid". True thyroid malignancy SNOMED needs identifying and adding. Search: "malignant neoplasm of thyroid gland" | `libs/domains/ncda_concept_sets.py` | Planned |
