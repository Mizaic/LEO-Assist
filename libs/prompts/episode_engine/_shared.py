"""Shared rules-of-the-road, vocabularies, and few-shot blocks reused
across every episode-engine prompt.

These are split out so the same wording is enforced in every stage and so
prompt diffs are easy to read.
"""

from __future__ import annotations

# -- Vocabularies (must match services/analysis_worker/app/episode_engine/schemas.py) --
MILESTONE_TYPE_LIST = (
    "referral, first_seen, diagnosis_confirmed, treatment_started, "
    "treatment_completed, benign_closure"
)
EPISODE_TYPE_LIST = "cancer, multi_site, benign, non_cancer, uncertain"
TREATMENT_TYPE_LIST = (
    "surgery, endocrine, chemotherapy, radiotherapy, immunotherapy, other"
)

# -- Common rules ----------------------------------------------------------
RULES_OF_THE_ROAD = """\
Rules of the road -- learnt from real GP records:

1. SAME-DAY ADMIN ECHOES
   A single clinical event explodes into many records on the same day:
     - the source clinical encounter (GP face-to-face, hospital letter,
       MDT outcome, structured problem-list entry with a code)
     - admin echoes: receptionist booking, patient text-message
       confirmation, prescription pickup, pharmacist drug review,
       clerical referral form, "Failed encounter" tasks
   Always identify the SOURCE encounter for an event. Admin echoes are NOT
   separate milestones.

2. RESTATEMENTS ARE NOT NEW EVENTS
   Phrases like "PMHx of X cancer", "history of X", "background of X",
   "post-mastectomy review", "cancer care review", "known X", or any
   recital that an earlier event happened, are NOT new milestones. The
   real event already fired earlier in the timeline (or in a prior
   episode).

3. STRUCTURED CODES ARE STRONG EVIDENCE
   Lines containing a Read or SNOMED code in parentheses (e.g. "Major:
   Mastectomy of right breast (XacLJ) (New Episode)" or "Two week wait
   referral (XaPyQ)") are higher-fidelity than free-text narration. The
   "(New Episode)" marker is a particularly strong signal of a real
   clinical event.

4. AUTHOR ROLE MATTERS
   Receptionist Access Role, Clerical Access Role, Admin/Clinical Support,
   "Pharmacist (Failed encounter)", and "N+S Encounter type" are almost
   never the source encounter for a clinical milestone. The source is
   typically a GP, nurse, consultant, or the medical secretary
   transcribing a hospital letter.

5. MULTIPLE EPISODES OVER TIME
   A patient can have several distinct cancer episodes over years
   (e.g. breast 2018 then colorectal 2024). These are SEPARATE episodes;
   do not merge them.

6. MULTI-SITE REFERRALS, SINGLE DIAGNOSIS
   When symptoms overlap, a patient may be referred via 2WW for two body
   sites (e.g. breast and ovarian) and one primary cancer is confirmed.
   This is ONE episode. The reconciler stage handles this; segmenter and
   classifier should still flag both windows so the reconciler can merge
   them.

7. TREATMENT TYPES
   Treatment events MUST be tagged with treatment_type. Neoadjuvant
   endocrine therapy (e.g. letrozole started before mastectomy) and the
   definitive surgery are BOTH real treatment_started milestones with
   different treatment_type values. Do NOT collapse them. Treatment type
   vocabulary: """ + TREATMENT_TYPE_LIST + """.

8. EVIDENCE QUOTES
   Every milestone must include an evidence_quote that is a literal
   substring of the source encounter text. Do not paraphrase.

9. WHEN UNSURE
   Set a low confidence and a frank reasoning. If you cannot find a
   defensible source encounter, set needs_human_review=true and explain.
"""


PATIENT_4802892365_REFERENCE = """\
Reference case (patient 4802892365, breast cancer):

Timeline summary:
  2025-03-26  GP enters PRISM 2WW referral for suspected breast cancer
              (multiple admin echoes the same day).
  2025-04-28  First seen in fast-track 2WW breast clinic.
  2025-05-02  Pharmacist "Failed encounter" mentioning letrozole
              prescribed by hospital. THIS IS NOT A TREATMENT EVENT.
  2025-05-19  Pharmacist drug review reconciles letrozole 2.5mg from
              Breast Clinic letter. THIS is the real treatment_started
              for neoadjuvant endocrine therapy.
  2025-05-19  Around this date, diagnosis confirmed (breast cancer ER+).
  2025-07-28  Mastectomy of right breast (XacLJ) (New Episode) entered
              by Medical Secretary. THIS is treatment_started for surgery
              (the definitive treatment).

Correct output: ONE cancer episode. Milestones:
  - referral 2025-03-26 (PRISM 2WW)
  - first_seen 2025-04-28 (fast-track clinic)
  - diagnosis_confirmed ~2025-05-19 (Breast Clinic letter reconciled)
  - treatment_started 2025-05-19 treatment_type=endocrine (letrozole
    neoadjuvant, real reconciliation, NOT the 02 May Failed encounter)
  - treatment_started 2025-07-28 treatment_type=surgery (mastectomy)

Incorrect output: a treatment_started on 2025-05-02 anchored on the
"Failed encounter" admin task -- this is the failure mode the rule-based
detector kept making.
"""
