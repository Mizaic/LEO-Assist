"""Shared rules-of-the-road, vocabularies, and few-shot blocks reused
across every episode-engine prompt.

These are split out so the same wording is enforced in every stage and so
prompt diffs are easy to read.
"""

from __future__ import annotations

# -- Vocabularies (must match services/analysis_worker/app/episode_engine/schemas.py) --
MILESTONE_TYPE_LIST = (
    "first_presentation, referral, first_seen, outcome_letter, "
    "diagnosis_confirmed, treatment_started, treatment_completed, "
    "benign_closure"
)
EPISODE_TYPE_LIST = "cancer, multi_site, benign, non_cancer, uncertain"
TREATMENT_TYPE_LIST = (
    "surgery, endocrine, chemotherapy, radiotherapy, immunotherapy, other"
)
PRESENTATION_PLACE_LIST = (
    "gp_surgery, gp_home_visit, other_primary_care, hospital_outpatient, "
    "hospital_inpatient, accident_and_emergency, walk_in_centre, "
    "out_of_hours, from_screening, telephone_consultation, "
    "email_consultation, video_consultation, dentist, optometrist, "
    "community_care_nurse, other, not_known"
)
DISRUPTION_CATEGORY_LIST = (
    "referral_lost_or_not_received, referral_rejected_or_returned, "
    "repeat_referral_required, appointment_dna, "
    "appointment_cancelled_by_patient, appointment_cancelled_by_trust, "
    "result_not_received_in_primary_care, letter_received_late, "
    "patient_unreachable, mdt_outcome_unclear, other_administrative_delay"
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


BREAST_REFERENCE_CASE = """\
Reference case (synthetic patient SYN-EE-001, breast cancer):

This is a synthetic teaching example. It illustrates the most common
failure mode of any rule-based detector: anchoring treatment_started
on an administrative "Failed encounter" task instead of the real
clinical reconciliation or definitive surgery.

Timeline summary:
  2025-03-12  GP face-to-face: patient reports a new right breast lump
              noticed two weeks ago. THIS is the real first_presentation
              that led to the eventual 2WW referral. Place = gp_surgery.
              At the end of the consultation the GP records: "advised
              to return urgently if the lump grows or skin changes
              appear before the clinic appointment." THIS is the
              safety_netting evidence for the episode.
  2025-03-26  GP enters PRISM 2WW referral for suspected breast cancer
              (multiple admin echoes the same day).
  2025-04-10  Patient phones reception: "no appointment letter from
              breast clinic yet"; reception task asks GP to chase. THIS
              is a disruption (category =
              referral_lost_or_not_received) -- record it but it does
              NOT change the referral milestone.
  2025-04-28  First seen in fast-track 2WW breast clinic.
  2025-05-12  Breast clinic outcome letter received in primary care --
              biopsy taken, awaiting histology. THIS is outcome_letter,
              not diagnosis_confirmed.
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
  - first_presentation 2025-03-12 presentation_place=gp_surgery
    (GP face-to-face for new breast lump -- the symptom that started
     the pathway)
  - referral 2025-03-26 (PRISM 2WW)
  - first_seen 2025-04-28 (fast-track clinic)
  - outcome_letter 2025-05-12 (biopsy-taken letter; not yet a diagnosis)
  - diagnosis_confirmed ~2025-05-19 (Breast Clinic letter reconciled)
  - treatment_started 2025-05-19 treatment_type=endocrine (letrozole
    neoadjuvant, real reconciliation, NOT the 02 May Failed encounter)
  - treatment_started 2025-07-28 treatment_type=surgery (mastectomy)

Plus an episode-level safety_netting record:
  recorded=true, date=2025-03-12, encounter_id=enc-presentation,
  evidence_quote="advised to return urgently if the lump grows
  or skin changes appear before the clinic appointment."

Plus one disruption:
  date=2025-04-10, category=referral_lost_or_not_received,
  description="Patient phoned: no appointment letter from breast
  clinic yet; GP chase requested.", encounter_id=enc-chase,
  evidence_quote="no appointment letter from breast clinic yet".

Incorrect output: a treatment_started on 2025-05-02 anchored on the
"Failed encounter" admin task -- this is the failure mode that
deterministic detectors kept making.
"""
