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

12. CLOSED WINDOW SCOPE
    If a window has a window_end date set, it represents a COMPLETED
    investigation pathway. Only emit milestones for events that actually
    COMPLETED within window_start to window_end. If an encounter within
    the window MENTIONS a future referral, appointment, or specialist visit
    planned for after window_end (e.g. "referred for upper GI investigation
    next week"), do NOT emit that as a milestone -- it is forward context,
    not a completed event in this window. The referral or appointment will
    belong to a different window that covers the later date.

13. PRIOR SCREENING "NORMAL" IS NOT A BLOCKER
    A past encounter with "breast neoplasm screening normal" (e.g. routine
    NHS Breast Screening Programme all-clear) does NOT mean the patient
    has no current breast cancer episode. Interval cancer, technical recall,
    and subsequent clinical records with "(New Episode)" and malignant
    or recall codes can start a genuine cancer pathway WEEKS LATER. Do NOT
    let an earlier "normal" letter block milestones on later windows.
    The cancer episode's first_presentation and referral are anchored to
    the RECALL / ASSESSMENT / first malignant structured code -- not the
    earlier routine clear, unless the clinical narrative explicitly
    re-interprets that encounter as a false negative (rare; usually the
    pathway begins at the new abnormal event).

14. NON-GP, A&E, AND ALTERNATIVE PRIMARY CARE ENTRY
    A pathway does not require a general-practice 2WW to exist.
    - first_presentation may be A&E, walk-in, out-of-hours, NHS 111,
      community nursing, or community pharmacy, with presentation_place
      set to accident_and_emergency, walk_in_centre, out_of_hours,
      other_primary_care, or community_care_nurse (etc.) as appropriate.
    - referral (pathway) is any documented handoff into the cancer work-up,
      including internal referral from ED/AMU, e-RS from hospital,
      or screening assessment booking -- not only a GP PRISM form.
    - Do not skip first_presentation because the only early record is
      A&E. Do not require a "GP referral" quote if the first pathway
      trigger is a hospital-issued or screening-issued handoff.

15. SAME-DAY SCREENING PLUS STRUCTURED MALIGNANCY (TYP. COLORECTAL)
    When TWO encounters on the SAME CALENDAR DATE are both part of one
    pathway, do not collapse them into a single row or demote the first.
    Common pattern: (1) a Bowel Cancer Screening routing / handoff to
    primary care, and (2) a second entry with a Read-coded
    "Malignant tumour of rectum" (or similar) with (New Episode). That
    day is still the episode start. Emit first_presentation on the
    encounter that records the screening pathway contact, with
    presentation_place=from_screening when the text is clearly the
    national bowel screening programme. Emit diagnosis_confirmed on the
    encounter that contains the literal malignant-code line (separate
    encounter_id, same date). If a handoff to the named practice is
    the only referral-like text, you may also emit a pathway
    "referral" on the encounter that best matches the handoff, or
    support it with a context tier -- do not invent a GP 2WW. Never
    shift window_start to a later day solely because the screening line
    and the malignancy line are different encounter_ids.

16. BCSP FOBT / FIT ABNORMAL AS FIRST PRESENTATION (NO GP YET)
    A Bowel Cancer Screening Programme (BCSP) result is often the first
    dated row: faecal occult blood (FOBT) or FIT "Abnormal", Read-coded
    lines, invitation to screening colonoscopy, and programme text such as
    "no need for GP action" (meaning the hub handles next steps, NOT that
    there is no presentation). This encounter IS the first_presentation
    for a screen-detected colorectal episode: set
    presentation_place=from_screening and use a literal evidence_quote
    from the result and programme lines. Do NOT require a later GP
    face-to-face before you emit first_presentation. If the only author
    line is "Receptionist Access Role" or similar, still use the record --
    the structured result and BCSP text are the source. A phrase
    "No Further Action" next to a receptionist-typed result may mean
    "no GP task" in the programme sense; it is NOT automatically
    benign_closure if the same or adjacent text records FOBT abnormal
    and colonoscopy follow-up. Do not confuse with a routine all-clear
    (compare rule 15 / breast screening "normal" patterns).
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
    (e.g. the 2WW form is a pathway "referral", the first clinical
    contact about the symptom is "first_presentation" -- GP, A&E, OOH,
    walk-in, or other primary / community)
  - After diagnosis_confirmed -> usually a CONTEXT milestone
    (e.g. a GP follow-up after treatment is "related_gp_visit",
    admin chasing of a clinic letter is "referral_admin")
  When you see a regex match that fires after the confirmed diagnosis on
  the same pathway, default to the matching CONTEXT type -- do NOT emit
  a duplicate pathway milestone for the same kind of event.

CONTEXT MILESTONE DEFINITIONS:

  - related_gp_visit          : a primary-care-SETTING consultation directly
                                related to this pathway but not the canonical
                                first_presentation. Includes: GP (F2F, telephone,
                                video, home), practice nurse, also NON-GP
                                primary and community (NHS 111 clinical call,
                                community pharmacist consultation, health
                                visitor, community / district nursing review
                                in the home) when the encounter is a pathway
                                follow-up, not the index A&E or specialist
                                event. A&E/ED is NOT "related_gp_visit" --
                                use it as first_presentation (index) or, for a
                                later A&E re-attendance, consider
                                related_specialist_visit for ED physician review
                                if the narrative is clearly secondary care.

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

  - related_specialist_visit   : a hospital / secondary-care or specialist
                                clinical contact related to the pathway but NOT
                                the canonical first_seen. Includes: follow-up
                                clinic visits, MDT outcomes, CNS/SCN reviews,
                                oncology appointments AFTER first_seen, and
                                a SUBSEQUENT A&E/AMU attendance where an acute
                                physician or ED specialist team documents further
                                pathway action (if not being used as
                                first_presentation for a new line of care).
                                The INDEX emergency attendance that starts the
                                episode is "first_presentation" with
                                presentation_place=accident_and_emergency, not
                                this context type.

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


MULTI_SITE_REFERENCE_CASE = """\
Reference case (synthetic patient SYN-EE-002, cough + upper-GI symptoms):

This illustrates the most common multi-site segmentation failure: merging a
GP-investigation-only "rule-out" window (Lung) into a continuing investigation
window (Upper GI) and using the wrong window_start date for both.

Timeline summary:
  2025-06-17  GP face-to-face: patient presents with persistent cough (4 weeks),
              weight loss, and occasional dysphagia. BOTH respiratory AND upper
              GI symptoms present at the SAME appointment.
              -> Open TWO windows at this date: one Lung, one Oesophageal.
              Both share window_start = 2025-06-17.

  2025-07-14  GP follow-up: CXR requested to exclude lung lesion. Upper GI
              investigations (stool test, bloods) also requested at same visit.
              Both windows are still open.

  2025-07-16  CXR result: normal, no lung lesion. GP records "CXR clear -- lung
              cancer excluded."
              -> Close the Lung window: window_end = 2025-07-16.
              The Oesophageal window remains open.

  2025-08-12  GP issues 2WW fast-track referral for suspected oesophageal
              cancer (dysphagia + weight loss). Oesophageal window continues.

  2025-08-27  Patient seen in upper GI fast-track clinic.

Correct output: TWO windows.
  Window 1 (Lung):        window_start=2025-06-17, window_end=2025-07-16
    GP-investigation-only pathway to exclude lung cancer. Closed by benign
    CXR result. No 2WW referral needed.
  Window 2 (Oesophageal): window_start=2025-06-17, window_end=null
    Upper GI pathway from first presentation, continuing through 2WW referral
    and clinic.

Incorrect output (the failure to avoid):
  A SINGLE "Oesophageal" window starting 2025-07-14, treating the CXR as a
  primary_care_investigation within the upper GI workup. This is wrong because:
  (a) It drops the Lung window entirely -- the rule-out pathway is invisible.
  (b) window_start 2025-07-14 misses the real first presentation (2025-06-17).
  Whenever a GP orders a CXR to "exclude lung lesion" alongside a GI workup,
  create a separate Lung window even if the CXR turns out to be normal.
"""


# Synthetic: same-day screening + same-day code-bearing malignancy;
# do not use real practice names, patient numbers, or dates from live charts.
COLORECTAL_SCREENING_SAME_DAY_REFERENCE = """\
Reference case (synthetic patient SYN-EE-003, colorectal, same day):

Two separate encounters on the same calendar date (different
encounter_ids) are common in bowel screening: one row records the
screening programme / routing contact; another records the
structured problem-list entry for the confirmed malignancy. BOTH are
the start of ONE episode. Do not drop the first row or set
window_start to the day after the screening line.

Example timeline (dates invented):
  2025-10-16 (morning) enc-a: "Bowel Cancer Screening to <named GP hub>"
    or similar handoff from the national programme to primary care.
    -> first_presentation on enc-a, presentation_place=from_screening
    (the screening pathway is the index presentation for an interval /
    screen-detected pathway; literal evidence from enc-a)

  2025-10-16 (afternoon) enc-b: "Malignant tumour of rectum (XE1vW)
    (New Episode)" and duplicate read line. -> diagnosis_confirmed on
    enc-b with a literal evidence_quote; same calendar date, distinct
    encounter_id from enc-a.

Segmenter: window_start = 2025-10-16 for the Colorectal window, not
2025-10-17, because the pathway evidence begins that day.

Incorrect output: a single "merged" first_presentation on enc-b
only, erasing the screening encounter; or omitting
first_presentation=from_screening because a GP 2WW is missing; or
anchoring the episode to enc-b as if enc-a were admin noise.
"""


# BCSP/FOBT positive: index row may have no GP; avoid inventing 2WW.
COLORECTAL_FOBT_BCSP_FIRST_REFERENCE = """\
Reference case (synthetic patient SYN-EE-004, colorectal, BCSP first):

A single early encounter (or a tight same-day pair) may contain only
the national Bowel Cancer Screening programme result -- no 2WW, no GP
consultation yet. Example phrases (fictional layout):

  "Bowel cancer screening programme: faecal occult blood result
   (XaPVj)"
  "FOBT Abnormal. Sent following a positive result. Participant will
   be invited for a screening colonoscopy. No need for GP action"
  "BCSP faecal occult blood test abnormal (XaPke)"
  Plus a result report line: Abnormal, reviewed under Receptionist
  Access Role.

Correct milestone handling:
  - first_presentation on this encounter (or the earliest of the same-day
    cluster), presentation_place=from_screening, evidence_quote from
    the abnormal / programme / colonoscopy invitation lines.
  - Do NOT omit first_presentation because "No need for GP action"
    appears, and do not wait for a PRISM 2WW from the practice.
  - diagnosis_confirmed only when histology, MDT, or a structured
    malignant-tumour code exists later; the FOBT row alone is
    first_presentation, not a confirmed cancer diagnosis.
  - If "No Further Action" appears in a receptionist note alongside
    Abnormal FOBT, prefer interpreting as programme / admin phrasing
    in context -- do not emit benign_closure for that snippet alone
    if the FOBT cluster shows an active screening work-up.

Segmenter: window_start on the first date of this BCSP-abnormal
evidence, not on a later arbitrary GP or colonoscopy date.

Incorrect output: no first_presentation until a GP is seen; or treating
     the receptionist-review row as ineligible for evidence_quote.
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
