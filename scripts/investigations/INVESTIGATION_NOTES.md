# Cancer Audit Data Quality Investigation Notes

Started: 2026-04-03
Author: Investigation session (see agent transcript cca66be5-85ea-41de-8018-3ff9a67066b3)

## Goal

Read every encounter for every patient, fix missing or incorrect coding, and use
what we learn to improve:
- The automated pipeline (anchor detection, episode building, exclusion detection)
- The LEO agent prompts (escalation, Ask LEO, deep dive narrative)
- The UX (cancer audit dashboard, no-referral cohort card, deep dive modal)

---

## What we have found so far

### 1. Episode-of-care data was mostly missing

The `EpisodeOfCare` nodes for cancer patients were sparse or missing because
`anchor_detector.py` had a critical bug: the Cypher query lacked a `WHERE patient_id`
clause and returned raw Node objects instead of scalar properties. Unit tests masked this
because they mocked already-flattened data. Fixed in this session.

After fixing the anchor detector, `remediate_episodes.py` was written to rebuild
all episodes from scratch with correct classification rules.

**Remediation script:** `scripts/remediate_episodes.py`
**Anchor fix:** `services/analysis_worker/app/analyzers/anchor_detector.py`

---

### 2. CANCER_HISTORY_IDS were leaking into confirmed_cancer

History-of-cancer codes (e.g. `H/O: malignant neoplasm`) were being treated as
active diagnoses, inflating the confirmed_cancer count. These should annotate
an episode but never confirm it on their own.

Fixed in `remediate_episodes.py` by separating `ACTIVE_DIAGNOSIS_IDS` from
`HISTORY_DIAGNOSIS_IDS` and only letting active codes confirm.

---

### 3. Weak exclusion codes were cancelling active diagnoses

"Normal appearance" (a bowel screening result) was present in some episodes
that also had a confirmed cancer code. Because exclusion detection ran after
diagnosis, these were being marked excluded. Fixed: weak exclusions are ignored
when an active diagnosis is present.

Concept sets involved:
- Weak: Normal appearance, non-specific NAD/no abnormality detected codes
- Strong: "No evidence of cancer found" (395100000), "No malignancy found on
  biopsy" (415068001), etc.

---

### 4. 9 "no-referral" confirmed cancer patients found

After remediation, 9 patients had `status = confirmed_cancer` but no
`referral_date` (no 2WW fast-track referral ever coded). These are currently
invisible to the standard cancer dashboard because all filters assume a referral
anchor exists.

These patients fall into roughly three categories:

#### Category A -- Cancer predates 2WW era or was registered historically
Codes appear on the problem list, no secondary care letters visible in the GP
record. May be historical. Needs human review.

Example: Patient 4587069337 (see §5 below).

#### Category B -- Emergency pathway bypassing 2WW
Patient presented acutely (e.g. A&E, walk-in centre) and cancer was found
incidentally via imaging or biopsy during that admission. GP received letters
and coded the diagnosis but never issued a 2WW.

Example: Patient 4742236882 (see §6 below).

#### Category C -- Secondary care problem-list codes
Cancer appears to have been diagnosed and managed entirely in secondary care.
GP received discharge summaries and coded the result, but the diagnosis
originated outside the GP record.

---

### 5. Patient 4587069337 (Mrs Jane Wallis) -- NEEDS REVIEW

**Finding:** `Malignant tumor of breast` coded June 2022, but the record shows
no cancer activity whatsoever for 23 months (Jun 2022 to May 2024).

**Gap analysis (every encounter read):**
- All encounters in the gap are entirely routine: BP monitoring, repeat
  prescriptions (atorvastatin, ramipril, naproxen, omeprazole), HbA1c, diabetic
  foot checks, bowel screening (FOBT normal Nov 2022), flu invites, UTI (Mar 2023),
  annual LTC diabetes/hypertension review (Apr 2023, Apr 2024).
- December 2023: walk-in centre attendance for a knee injury. PMH listed by
  the LUTC nurse as "hypertensive, type II diabetic" -- breast cancer is NOT
  mentioned.
- Annual LTC review April 2023: full blood count, LFT, lipids, HbA1c, cholesterol,
  TSH, foot check -- all routine. No cancer mentioned by any clinician.
- Annual LTC review April 2024: BP 177/79, full bloods again -- no cancer mention.

**Pivot event (May 2024):**
- NHS Breast Screening Programme letter received: "Breast neoplasm screening
  normal" (SNOMED 68620). This is a normal mammogram result.

**Conclusion:** The 2022 coding is almost certainly a HISTORICAL diagnosis --
previously treated breast cancer copied from a hospital letter or problem list.
The fact that she was invited to and received a normal breast screening result
in May 2024 strongly suggests the cancer was not active. A live active cancer
patient would not receive a normal mammogram from the screening programme.

**Recommended action:** Episode should be reclassified. `condition_type` remains
`breast`. `status` should be set to `needs_review` with flag `HISTORY_PRESENT`.
A human reviewer should confirm whether this is a resolved/historical cancer or
an active one being managed silently in secondary care.

**EpisodeOfCare episode_id:** TBC -- check remediation output for this patient.
**Next step:** Add `HISTORY_PRESENT` flag and set `needs_review = true`.

---

### 6. Patient 4742236882 (Mrs Valerie Thorburn) -- EMERGENCY PATHWAY

**Full referral pathway (reconstructed from all encounters):**

| Date | Event |
|------|-------|
| Jan 2026 (corrected: Jan 2025) | First GP contact: Dr Vadher, right lower back pain 1-week history. Diagnosed muscle sprain, co-codamol prescribed. |
| 29 Jan 2025 | Review: no improvement, switched to naproxen + PPI. Baseline U+Es requested. Dr Bridges notes at debrief: "NOTE lack of presentations historically -- ?relevant." |
| 5 Feb 2025 | U+Es: eGFR 35, creatinine 123. Flagged abnormal. Repeat in 6 weeks arranged. |
| 10 Feb 2025 | Self-attends Loughborough Urgent Treatment Centre (LUTC). Diagnosed lumbar sprain. Also referred to LLR MSK Physiotherapy. |
| 26 Feb 2025 | **Pivotal GP encounter.** Dr Selvamogan: 10/10 right flank pain, nausea, absent bowel sounds, 3 days no bowel movement. Severe RUQ/flank tenderness. PMH: "has not seen a doctor in many years." Brother died of oesophageal cancer. Impression: renal colic / biliary colic / bowel obstruction. Plan: **emergency ED admission**. Supervisor Dr Patel: "needs urgent ED review today." |
| 27 Feb -- 4 Mar 2025 | **UHL admission under Mr Dennison AR.** MRCP, CT abdomen/pelvis, bone profile. Findings: metastasis to bone of unknown primary, hypercalcaemia, new-onset AF, gallstones with biliary dilatation. |
| 14 Mar 2025 | Breast Surgeon letter received. Left breast USS, mammogram, biopsy of left breast and left axillary lymph nodes. |
| 24 Mar 2025 | Results: **Infiltrating duct carcinoma (left breast)** confirmed. Axillary USS malignant-looking nodes. Metastasis to lymph node (left axilla) confirmed. CT abdomen/pelvis done. |
| 3 Apr 2025 | MRI spine: **metastatic spinal cord compression**. Palliative radiotherapy started. Second UHL admission (3-16 Apr 2025). |
| 29 Apr 2025 | **Letrozole 2.5mg** (hormone therapy) and Adcal-D3 started. Pharmacist notes radiation-related diarrhoea. |

**Why no 2WW:** Cancer found through emergency pathway, not GP-initiated fast-track.
The back pain and hypercalcaemia that prompted the ED referral were the first
clinical signs. GP acted correctly and immediately.

**Current status (Apr 2025):** Active treatment -- letrozole, edoxaban (for new AF),
bisoprolol, Adcal. Community therapy (reablement/rehab) involved. MSK physiotherapy
referral abandoned given the diagnosis. Daughter Jayne is primary carer.

**EpisodeOfCare:** `condition_type = breast`. `status = confirmed_cancer`.
`referral_date = NULL`. `deep_dive_status = TBC` once deep-dive agent built.

---

## Patterns and system improvements identified

### Pipeline improvements needed

| Issue | Impact | Recommended fix |
|-------|--------|-----------------|
| Anchor detector had no patient_id WHERE clause | All patients -- no episodes were built | Fixed |
| CANCER_HISTORY_IDS treated as active diagnosis | Over-counting confirmed_cancer | Fixed in remediation |
| Weak exclusion codes cancelling active diagnoses | Under-counting confirmed cancer | Fixed in remediation |
| `condition_type = unknown` for many no-referral patients | Dashboard can't filter by tumour site | Needs targeted update for 9 patients |
| No-referral episodes invisible to dashboard | 9 confirmed cancer patients hidden | New cohort card needed |
| episode_id not always populated on EpisodeOfCare | Episodes can't be addressed individually | Remediate to ensure deterministic IDs |

### Concept set improvements needed

| Concept set | Issue |
|-------------|-------|
| `CANCER_TYPE_IDS` | May miss some site-specific subtypes -- review against SNOMED hierarchy |
| `CANCER_HISTORY_IDS` | Good list but some codes may appear in both active and historical contexts -- needs disambiguation by assertion tag |
| `CANCER_EXCLUSION_IDS` | Weak vs strong distinction needed (already in remediate_episodes.py, needs propagating to ncda_concept_sets.py) |
| Fast-track referral concepts | Some patients have referral codes that are site-adjacent but not in the set -- check `snomed_ncda_fast_track_referrals_mapping.json` for completeness |

### LLM / agent improvements needed

| Area | Issue | Improvement |
|------|-------|-------------|
| Ask LEO escalation | Doesn't know about no-referral episodes -- treats all cancer as referral-anchored | New context note about no-referral pathway types |
| Extraction prompt | May not flag hypercalcaemia + bone pain as a cancer signal | Add to clinical context instructions |
| Disorder verifier | Good at confirming diagnoses, but doesn't reason about pathway type | Out of scope for now |
| Deep-dive agent | Does not exist yet | Build it (see architecture in investigation notes) |

### UX improvements needed

| Area | Improvement |
|------|-------------|
| Cancer audit dashboard | New "no-referral cancer" cohort card (count + list + Analyse button) |
| Episode timeline | Deep-dive narrative modal (using existing `agent_reasoning` field) |
| Cohort filters | Add `no_referral` as a filterable episode flag |
| Review queue | Surface `HISTORY_PRESENT` flagged episodes for human review |

---

## What to do next: full encounter read and fix plan

### Phase 1 -- Read all encounters for the 9 no-referral patients (Priority)

For each of the 9 patients:
1. Read every encounter chronologically (like `_gap_read.py` approach)
2. Identify: presentation, referral, diagnosis, treatment, why no 2WW
3. Fix `condition_type` where currently `unknown`
4. Set `needs_review = true` for any HISTORY_PRESENT cases
5. Record findings in this file

Known patients and their status:

| Patient ID | Known condition | Current episode status | Notes |
|------------|----------------|----------------------|-------|
| 4587069337 | Breast | confirmed_cancer (NEEDS REVIEW) | May be historical -- breast screening normal May 2024 |
| 4742236882 | Breast (metastatic) | confirmed_cancer | Emergency pathway, GP referred to ED Feb 2025. Active treatment. |
| Others (7 TBC) | Various | TBC | Investigate individually |

### Phase 2 -- Broaden to all cancer patients (74+)

Run a structured encounter-read pass for all patients where:
- `status = confirmed_cancer` but `diagnosis_date` is > 2 years ago with no
  treatment codes in the encounter record
- `status = needs_review` (any flag)
- `status = pending` (no outcome coded after >6 months)
- Any patient where `MIXED_OUTCOME` was flagged during the referral episode analysis

### Phase 3 -- Fix coding gaps

For each patient where encounter text reveals a clinical event that is not coded:
- Identify the missing SNOMED concept
- Determine whether it should be a `DOCUMENTS` relationship (coded from text)
  or a problem-list entry (clinical_finding on the patient)
- Create a HITL task (`ExclusionAudit` or `CodingDecision` node) for human review
  rather than auto-writing, since this affects a medical device's audit output

### Phase 4 -- Extract learning for agents and concept sets

For each investigation:
1. Was the clinical signal present in the encounter text? (yes/no)
2. If yes, was it coded? (yes/no)
3. If coded, was it in our concept set? (yes/no)
4. If in concept set, was it used correctly by the pipeline? (yes/no)
5. Gap identified -> update concept set / pipeline / prompt accordingly

Track this as a structured table in `LEARNING_LOG.md` (to be created).

---

## Session 2 findings (2026-04-03, continued)

### 6. REFERRAL_SITE and SPECIALIST_SITE mappings were completely scrambled

The `REFERRAL_SITE` and `SPECIALIST_SITE` dictionaries in `remediate_episodes.py`
had the site labels rotated/misaligned relative to the SNOMED concept IDs.
Almost all 12 entries were wrong (e.g. 276401000000108 = head_and_neck was
mapped to "colorectal"). This affected every episode's `condition_type` and
`referral_site`. Fixed in `scripts/remediate_episodes.py`. **Remediation must
be re-run on all patients.**

### 7. Patient 6230411040 is outside the audit window

Diagnosis date 2010-01-06. This patient should be deleted entirely.
Safe deletion script: `scripts/investigations/safe_delete_patient.py`.
Usage: `python safe_delete_patient.py --patient-id 6230411040 --apply`

### 8. Patient 7306752529 (Farshid Ershadi) -- root cause identified

**Clinical story**: 35-year-old male. Borderline TSH from 2023. GP found
anterior neck mass (goitre) in March 2024, growing for 3-4 months, 5 kg weight
loss. Fast-track 2WW for head and neck cancer made 7 March 2024 (EMIS code
XaMkD). USS March 2024, ENT appointment 3 April 2024, diagnostic nasendoscopy
April 2024. Partial thyroidectomy May 2024. Histology: encapsulated poorly
differentiated thyroid carcinoma. Second hemithyroidectomy July 2024. I-131
therapy (Radioiodine) November 2024. Under oncology. December 2025: neck
dissection for disease progression. Still on levothyroxine suppression therapy,
monitoring TSH and thyroglobulin.

**Root cause of no-referral**: The EMIS code XaMkD was not mapped to SNOMED
276401000000108 in the Neo4j DOCUMENTS relationships. The 2WW referral encounter
(2024-03-07) has no concept node attached. Both the remediation script and the
anchor detector therefore could not see it. This is an EMIS-to-SNOMED mapping
gap in the ingestion pipeline.

**Data fix**: `scripts/investigations/fix_7306752529.py --apply`
adds the Situation node and DOCUMENTS relationship, then corrects the episode.

**Pipeline fix required**: The ingestion pipeline must map EMIS code XaMkD
(and all fast-track referral EMIS codes) to their SNOMED equivalents. The
EMIS-SNOMED mapping table needs auditing for all 14 fast-track referral codes.

### 9. Patient 4562218347 (Theresa Reynolds) -- screening-detected breast cancer

**Clinical story**: ~71-year-old female. Normal FOBT bowel screening Jan 2023.
Jan 2024: fatigue workup -- all bloods normal. May 31, 2024: breast clinic
letter back to GP with diagnosis -- invasive ductal carcinoma (BB91.), right
breast (infiltrating duct carcinoma). Mammogram and USS at breast clinic.
June 2024: wide local excision + sentinel node biopsy + mammoplasty. Oct 2024:
started letrozole 2.5mg for 5 years (discussed with oncologist Dr Sampson).
Nov 2024: radiotherapy completed. May 2025: patient declined to continue
letrozole (reviewed by oncologist). May 2025: "No evidence of recurrence of
cancer (414861001)". Aug 2025: Shingrix vaccination -- post-treatment
immunosuppression prevention. Oct 2025: new hypertension requiring treatment.
CXR to exclude lung lesion -- normal. DEXA scan planned 2028. Still in
follow-up with breast clinic.

**Why no 2WW**: Cancer was detected through NHS breast screening mammography
(age 50-71 recall programme), not through GP-referred 2WW. No GP-initiated
fast-track referral is expected. This is the CORRECT clinical pathway for
screening-detected cancers.

**Data action**: Episode should be updated:
- `condition_type = "breast"` (currently "unknown")
- `referral_site = "screening"` (not "no_referral")
- `status = "confirmed"` (correct)
- `needs_review = false`
- Add flag `SCREENING_DETECTED`

### 10. Patient 4563706582 (Leslie Bailey) -- gastric/oesophageal cancer (terminal)

**Clinical story**: Older male with type 2 diabetes, obesity, depression. FOBT
normal July 2023. LUTS March 2024 (enlarged smooth prostate). Iron deficiency
anaemia Dec 2024 (Hb 122, MCV 79) with loss of appetite and constipation.
Endoscopy referral sent Dec 2, 2024. Jan 14, 2025: biopsy of gastrointestinal
tract + "Carcinoma of stomach" coded. Jan 22, 2025: "cancer in his stomach --
told at endoscopy". CT scan. Jan 31, 2025: "Carcinoma of oesophagus (X78g3) -
junctional" added. Feb 21, 2025: staging laparoscopy cancelled -- deemed not
a surgical candidate, prognosis months. April 2025: specialist confirmed no
surgical Rx, prognosis months, MacMillan involved. Patient started on palliative
pathway. LOROS hospice day therapy from summer 2025. Dec 2025: losing weight,
pain on eating, on Sevodyne patches for pain. Dec 9, 2025: nutrition referral
(MUST score 2 -- high risk malnutrition). On morphine for pain.

**Why no 2WW**: IDA and anorexia were the presenting symptoms. GP appropriately
did FIT test (result 4 ug/g -- technically low risk for CRC but done with IDA
context) and sent an urgent endoscopy referral (not a coded 2WW fast-track). The
endoscopy found cancer. This is a GENUINE missed 2WW opportunity -- the IDA
with weight loss and appetite loss in an older man should have triggered a
lower GI or upper GI 2WW referral. Instead an "endoscopy referral" was sent
which is a different pathway.

**Key learning**: NICE NG12 criteria for 2WW upper GI include: unexplained weight
loss + epigastric pain/dysphagia; and dyspepsia age >55 with weight loss, iron
deficiency, or vomiting. This patient met criteria. The GP may have sent the
referral through the endoscopy direct-access route rather than the 2WW pathway.

**Data action**:
- `condition_type = "upper_gi"` (stomach/oesophageal junctional)
- `referral_site = "endoscopy_direct_access"` (not standard 2WW)
- `status = "confirmed"`
- Add flag `MISSED_2WW_OPPORTUNITY`, `PALLIATIVE`
- `needs_review = false` (clear clinical picture)

### 11. Patient 4992507875 (Lilian Mapombi) -- DFSP skin (sarcoma)

**Clinical story**: Female. Oct 2016: GP assessed 2mm slightly raised mole
on left cheek -- reassured benign, "Naevus (X75uF)", "No evidence of cancer
found (395100000)" coded. Then long gap with no cancer-related encounters.
Oct 2024 (8 years later): Dr Noble (GP) examines a lump on left thigh,
"noticed 4/52 ago, has increased in size since... 2.5mm, soft, pink lesion
central..." -- coded as "Pigmented dermatofibrosarcoma protuberans (X77oW)".
Simultaneously, knee X-ray requested and "History of malignant neoplasm
(266987004)" coded. Patient has 500 encounters total but only 13 signal
encounters, mostly in Oct 2024.

**Why no 2WW**: DFSP (Dermatofibrosarcoma Protuberans) is a rare, locally
aggressive soft tissue sarcoma. It is treated by sarcoma teams, not standard
dermatology. The appropriate pathway would be a 2WW sarcoma referral. However,
it appears the GP is managing this locally (coding the diagnosis themselves)
without a 2WW. This may have been referred through a sarcoma MDT route that is
not captured in primary care records, OR it was managed via the dermatology
direct-access route. Without more encounter data it is unclear.

**Data quality note**: The concept cid=372130007 is labelled "Malignant neoplasm
of skin" in Neo4j but the SNOMED preferred term for 372130007 is "Malignant
neoplasm of haematopoietic and related tissue". The DFSP concept in the EMIS
record (X77oW = Pigmented dermatofibrosarcoma protuberans) has been mapped to
the wrong SNOMED concept. Correct SNOMED for DFSP is likely 40012004 or a
descendant. This is a mapping error in the knowledge graph.

**Data action**:
- `condition_type = "sarcoma"` (DFSP is classified as a sarcoma)
- `referral_site = "no_referral"` (may remain until pathway clarified)
- Add flag `NEEDS_PATHWAY_CLARIFICATION`
- `needs_review = true` (sarcoma without a 2WW is clinically significant)

### 12. Patient 4202301609 -- haematology biopsy confirmed

**Clinical story continued**: Aug 2025 FIT positive -> 2WW colonoscopy -> polyps
only. CT Sept 2025: left renal lesion described as "nodal in nature" -- lymphoma
team consulted internally at secondary care (NOT a GP 2WW, an internal secondary
care referral). Nov 2025: retroperitoneal mass identified. CT-guided biopsy Nov
13, 2025. Nov 14 nursing note: "retroperitoneal mass concerning for lymphoma...
emergency admission with ruptured part of kidney... nephrostomy inserted... biopsy
1/7 ago." Nov 26: coded "Primary malignant neoplasm of unknown site (310504009)".

**Answer to user question**: Yes -- there was an internal haematology referral
(secondary care, not GP-initiated 2WW). The lymphoma team was consulted by the
urologists/radiologists after CT showed a nodal-looking renal lesion. This is an
INTERNAL tertiary referral within secondary care, not a GP-initiated 2WW pathway.
The GP-initiated route was via colonoscopy/lower GI, which was the presenting
2WW. The haematology involvement came after the cancer was already in secondary
care investigation.

**Outstanding**: Biopsy result not yet in the GP record at the time of the data
cut. Diagnosis is provisionally coded as "unknown primary" which may update once
histology confirmed. If lymphoma confirmed, `condition_type` should become
"haematology".

---

## Scripts produced in this investigation

| Script | Purpose | Status |
|--------|---------|--------|
| `scripts/audit_cancer_status.py` | Initial audit of cancer diagnosis/exclusion status | Retained |
| `scripts/analyse_referral_episodes.py` | Cluster referrals into episodes, classify outcomes | Retained |
| `scripts/remediate_episodes.py` | Full episode rebuild with corrected rules | Retained |
| `scripts/investigations/safe_delete_patient.py` | Safely delete a patient and all data | Retained |
| `scripts/investigations/fix_7306752529.py` | Fix missing SNOMED link + episode for thyroid patient | Retained |
| `scripts/investigations/_read_no_referral_patients.py` | Read all encounters for no-referral patients | Retained |
| `scripts/_gap_read.py` | Read all encounters in a date gap for one patient | Deleted after use |
| `scripts/_referral_check.py` | Pull referral details for a specific patient | Deleted after use |
| `scripts/_deep_dive_patients.py` | Deep chronological dive for two specific patients | Deleted after use |
| `scripts/_check_no_referral.py` | Retrieve diagnoses/treatments for no-referral group | Deleted after use |
| `scripts/_verify_remediation.py` | Verify EpisodeOfCare node counts post-remediation | Deleted after use |
| `scripts/_assess_mixed_outcomes.py` | Resolve MIXED_OUTCOME episodes using encounter text | Deleted after use |

---

## Architecture planned (not yet built)

See agent transcript for full design. Summary:

1. `libs/cypher/no_referral_queries.py` -- new Cypher queries for no-referral cohort
2. `services/analysis_worker/app/analyzers/deep_dive_analyzer.py` -- worker job
3. `services/analytics_api/app/routers/no_referral.py` -- two endpoints
4. `services/ui/src/components/operations/DeepDiveNarrativeModal.tsx` -- UI modal
5. New UN, DI (x2), Risk (x2), VT, traceability matrix updates

---

## Open questions

1. For patient 4587069337 -- is the 2022 breast cancer code a historical problem-list
   entry or an active diagnosis? Need GP to confirm. Episode should stay `needs_review`
   until confirmed.

2. For the 7 other no-referral patients -- are they also emergency/incidental pathways
   or are there other explanations (e.g. private diagnosis, diagnosis in another system)?

3. Should `no_referral` episodes be included in the QOF cancer register count? If the
   cancer was confirmed, they probably should be -- but the pathway compliance metric
   (2WW referral rate) should correctly show 0% 2WW for this cohort.

4. What is the threshold for triggering a deep-dive agent automatically (on episode
   creation) vs on-demand (clinician clicks Analyse)? On-demand is safer for a medical
   device -- avoids autonomous narrative generation without human intent.

5. How should the deep-dive narrative be stored? `EpisodeOfCare.agent_reasoning` already
   exists and flows to `EpisodeTimelineView`. This is the natural store. But we should
   version it and record who triggered the analysis and when.

---

## References

- Agent transcript: cca66be5-85ea-41de-8018-3ff9a67066b3
- Remediation script: `scripts/remediate_episodes.py`
- Concept sets: `libs/domains/ncda_concept_sets.py`
- Anchor detector fix: `services/analysis_worker/app/analyzers/anchor_detector.py`
- SNOMED referral mapping: `configs/snomed/snomed_ncda_fast_track_referrals_mapping.json`
- SNOMED specialist mapping: `configs/snomed/snomed_ncda_seen_by_specialist_mapping.json`
- SNOMED outcome mapping: `configs/snomed/snomed_ncda_referral_outcomes_mapping.json`
