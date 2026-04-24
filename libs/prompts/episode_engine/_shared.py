"""Shared rules-of-the-road, vocabularies, and few-shot blocks reused

Atlas trace:
  DO: DO-710D9EEB
  DI: DI-CBCA6E2D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-710D9EEB")

across every episode-engine prompt.

These are split out so the same wording is enforced in every stage and so
prompt diffs are easy to read.
"""

from __future__ import annotations

# -- Vocabularies (must match services/analysis_worker/app/episode_engine/schemas.py) --
# Pathway tier: canonical nine (eight from the LLM + care_obstruction from
# the anchor detector). These feed episode date roll-ups.
PATHWAY_MILESTONE_TYPE_LIST = (
    "first_presentation, referral, first_seen, outcome_letter, "
    "diagnosis_confirmed, treatment_started, treatment_completed, "
    "benign_closure"
)

# Context tier: supporting evidence that gives the reviewer the full
# narrative of the pathway. Authorised for AI emission by DI-2C015ADE.
# NEVER feed episode date roll-ups.
CONTEXT_MILESTONE_TYPE_LIST = (
    "related_gp_visit, primary_care_investigations, referral_admin, "
    "referral_sent, related_specialist_visit, specialist_diagnostics, "
    "related_correspondence"
)

# Combined list exposed to prompts that need both tiers.
MILESTONE_TYPE_LIST = PATHWAY_MILESTONE_TYPE_LIST + ", " + CONTEXT_MILESTONE_TYPE_LIST
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
RULES_OF_THE_ROAD = (
    """\
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
   vocabulary: """
    + TREATMENT_TYPE_LIST
    + """.

8. EVIDENCE QUOTES
   Every milestone must include an evidence_quote that is a literal
   substring of the source encounter text. Do not paraphrase.

9. WHEN UNSURE
   Set a low confidence and a frank reasoning. If you cannot find a
   defensible source encounter, set needs_human_review=true and explain.

10. BENIGN OUTCOMES
    If an episode ends in benign_closure (investigation confirmed no cancer
    or cancer is ruled out), you MUST NOT emit "diagnosis_confirmed".
    benign_closure and diagnosis_confirmed are mutually exclusive terminals.
    Also MUST NOT emit "treatment_started" or "treatment_completed" for a
    purely benign episode (no cancer found, no pre-malignant treatment).
    The sequence for a benign investigation pathway is:
      first_presentation -> referral -> [first_seen] -> benign_closure
    Intermediate context milestones (primary_care_investigations,
    related_gp_visit, specialist_diagnostics) are fine IF there is a
    literal source encounter for them.

11. FIRST_SEEN REQUIRES A CLINIC VISIT
    Only emit first_seen when there is an explicit outpatient or fast-track
    clinic attendance record (e.g. "2WW clinic", "outpatient letter",
    "Consultant review", hospital appointment). Do NOT emit first_seen for
    open-access investigations (colonoscopy booked directly, CT/MRI
    reported to GP) that occur without a preceding outpatient clinic visit.
    Open-access investigations belong to specialist_diagnostics, not
    first_seen.
"""
)


CONTEXT_MILESTONE_RULES = """\
Context-tier milestones -- supporting evidence for the reviewer narrative:

These seven types exist so the reviewer can see the FULL pathway, not just
the canonical anchor events. They NEVER feed date roll-ups. Every context
milestone MUST have a literal evidence_quote and a clear reasoning.

KEY TEMPORAL DISAMBIGUATION RULE -- READ CAREFULLY:
  Regex patterns and text mentions of "referral", "GP visit", "bloods",
  "appointment letter" appear BOTH before and after diagnosis_confirmed.
  The milestone type is determined by WHEN it occurs AND its clinical
  purpose:
  - Before diagnosis_confirmed -> usually a PATHWAY milestone
    (e.g. the 2WW form is a pathway "referral", the first GP appointment
    about the symptom is "first_presentation")
  - After diagnosis_confirmed -> usually a CONTEXT milestone
    (e.g. a GP follow-up after treatment is "related_gp_visit",
    admin chasing of a clinic letter is "referral_admin")
  When you see a regex match that fires after the confirmed diagnosis on
  the same pathway, default to the matching CONTEXT type -- do NOT emit
  a duplicate pathway milestone for the same kind of event.

CONTEXT MILESTONE DEFINITIONS:

  - related_gp_visit          : a GP / primary-care consultation directly
                                related to this pathway but not the canonical
                                first_presentation. Includes telephone/video
                                GP calls to discuss ongoing care, GP reviews
                                during treatment, and carer calls.

  - primary_care_investigations: blood tests, urine tests, ECG, plain X-ray,
                                or any other investigation REQUESTED BY GP
                                (not ordered by the hospital specialist).
                                Hospital-requested tests are specialist_diagnostics.

  - referral_admin             : administrative handling of the referral that
                                is NOT the referral itself. Includes: choose-and-
                                book admin, receptionist follow-up, chasing an
                                appointment letter, re-booking after DNA, e-RS
                                tasks. A 2WW form being SENT is "referral_sent";
                                chasing it up afterwards is "referral_admin".

  - referral_sent              : the Medical Secretary / admin encounter that
                                CONFIRMS the 2WW form was sent and processed.
                                Text hallmarks: "Fast track referral for
                                suspected X cancer (XaMeC)", "Choice and booking
                                enhanced services administration (XaMJa)",
                                "Patient awaiting OPD appt.: Yes 2ww". This is
                                ALWAYS a DIFFERENT encounter_id from the pathway
                                "referral" milestone (which captures the GP's
                                clinical decision). On the same day you will see
                                TWO records: the GP's consultation firing
                                "referral" AND the Medical Secretary's admin entry
                                firing "referral_sent". HARD RULE: if you have
                                already emitted a pathway "referral" for encounter
                                X, you may still emit "referral_sent" for a
                                DIFFERENT encounter Y on the same day -- they are
                                genuinely separate records. Only skip
                                "referral_sent" if the SAME encounter_id already
                                carries the pathway "referral" milestone.
                                Exception to the temporal rule: referral_sent
                                fires pre-diagnosis (alongside the pathway
                                referral), NOT post-diagnosis.

  - related_specialist_visit   : a hospital / specialist outpatient visit related
                                to the pathway but NOT the canonical first_seen.
                                Includes: follow-up clinic visits, MDT outcomes,
                                nurse specialist consultations, oncology review
                                appointments AFTER first_seen.

  - specialist_diagnostics     : investigations ORDERED BY THE SPECIALIST:
                                biopsy, CT, MRI, PET-CT, mammography,
                                colonoscopy, bronchoscopy, bone marrow biopsy,
                                and similar secondary-care investigations.
                                GP-requested blood tests are
                                primary_care_investigations,
                                not specialist_diagnostics.

  - related_correspondence     : clinic letters, discharge summaries, MDT
                                outcome letters, or other written correspondence
                                received in primary care from the hospital team.
                                These are documents ABOUT the pathway, not the
                                clinical event itself. A single encounter may
                                carry both a pathway milestone (e.g.
                                outcome_letter, diagnosis_confirmed) AND a
                                related_correspondence tag if the document also
                                happens to be the letter-received record.

IMPORTANT: context milestones DO NOT replace pathway milestones. Both can
fire for the same encounter (e.g. a biopsy result letter that confirms the
diagnosis fires BOTH "diagnosis_confirmed" AND "related_correspondence").
"""


CANCER_TYPE_PICKER = """\
Choosing suspected_site -- the canonical NCDA tumour categories:

The suspected_site field MUST be one of the canonical NCDA cancer
types. The schema enforces this with an enum, but be deliberate about
the choice:

- Pick the SPECIFIC body site whenever the encounter text supports it
  (e.g. 'Breast', 'Colorectal', 'Prostate', 'Lung', 'Melanoma',
  'Lymphoma'). Always prefer the most specific site over a pathway
  name (e.g. emit 'Oesophageal' rather than relying on 'Other' for
  upper-GI cases when the oesophagus is named).

- Use 'Unknown Primary' when the timeline genuinely contains a
  metastatic / cancer-of-unknown-primary referral and no primary site
  is named.

- Use 'Other' for cancers that exist outside the standard NCDA list
  (e.g. salivary gland, anal canal where the lower-GI / colorectal
  pathway label is wrong, cardiac tumours).

- Use 'No Information' only when the timeline contains no clinical
  evidence of any cancer site for this window (admin echoes only).

- For dermatology / suspected skin cancers without a specific tumour
  type, prefer 'Melanoma' (the dominant NCDA skin entry); only fall
  back to 'Other' for explicit non-melanoma skin cancers.

- For ambiguous head-and-neck referrals, prefer 'Oropharyngeal'
  unless 'Thyroid' or 'Laryngeal' is named explicitly.
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
