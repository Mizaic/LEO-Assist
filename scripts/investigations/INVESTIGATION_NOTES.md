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

Example: internal review patient (synthetic id in test fixtures only).

#### Category B -- Emergency pathway bypassing 2WW
Patient presented acutely (e.g. A&E, walk-in centre) and cancer was found
incidentally via imaging or biopsy during that admission. GP received letters
and coded the diagnosis but never issued a 2WW.

Example: internal review patient (synthetic id in test fixtures only).

#### Category C -- Secondary care problem-list codes
Cancer appears to have been diagnosed and managed entirely in secondary care.
GP received discharge summaries and coded the result, but the diagnosis
originated outside the GP record.

---



## Case narratives (removed from VCS)

Detailed per-patient timelines, clinician names, locations, and free-text case
studies were removed from this document to keep the repository free of
identifiable information. Retain pipeline findings, design controls, and
non-identifying audit summaries in internal systems.

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
| 9990002006 | Breast | confirmed_cancer (NEEDS REVIEW) | May be historical -- breast screening normal May 2024 |
| 9990002001 | Breast (metastatic) | confirmed_cancer | Emergency pathway, GP referred to ED Feb 2025. Active treatment. |
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

### 7-12. Further case work (narrative removed)

Additional session notes covered: patients outside the audit window (deletion
via `safe_delete_patient.py` only with explicit id arguments), an EMIS `XaMkD`
to SNOMED `276401000000108` **DOCUMENTS** mapping gap for head-and-neck 2WW,
screening-detected breast, direct-access endoscopy vs 2WW, DFSP / SNOMED
mapping quality, and secondary-care-only haematology consultation. **Do not
commit timelines, names, or locations**; keep detailed findings in
non-repository evidence stores.

---

## Scripts produced in this investigation

| Script | Purpose | Status |
|--------|---------|--------|
| `scripts/audit_cancer_status.py` | Initial audit of cancer diagnosis/exclusion status | Retained |
| `scripts/analyse_referral_episodes.py` | Cluster referrals into episodes, classify outcomes | Retained |
| `scripts/remediate_episodes.py` | Full episode rebuild with corrected rules | Retained |
| `scripts/investigations/safe_delete_patient.py` | Safely delete a patient and all data | Retained |
| *(one-off, local only)* | Ad-hoc DOCUMENTS / episode fix for a thyroid mapping gap | Do not commit patient-specific script names or ids |
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

1. For patient 9990002006 -- is the 2022 breast cancer code a historical problem-list
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
