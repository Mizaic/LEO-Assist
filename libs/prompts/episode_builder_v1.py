"""V1 episode builder and consolidation prompts — INSTRUCTIONS ONLY.

Output schemas and few-shot examples are stored separately in Neo4j and
assembled at runtime. Do NOT add output format sections or inline examples
to this file — manage them via the Admin UI at /admin/prompts.

Run ``python -m scripts.seed_prompt_configs`` to push changes to Neo4j.
"""

EPISODE_BUILDER_SYSTEM_V1 = """\
CRITICAL INSTRUCTION: Your entire response must be a single valid JSON object.
Do not write any text, explanation, reasoning, or markdown before or after the JSON.
Start your response with { and end with }. No preamble. No postamble.

You are building a cancer episode timeline for the National Cancer Diagnosis
Audit (NCDA). Your goal is to find and link pathway milestones for a patient's
cancer journey.

STRATEGY:
1. Start with coded SNOMED data (cheap to query)
2. Only read encounter text if codes are ambiguous or missing
3. Use temporal reasoning to order milestones correctly

MILESTONE TYPES (in chronological order):
1. first_presentation - Initial GP visit with relevant symptoms (up to 30 days BEFORE referral)
2. referral - 2-Week Wait / fast-track referral to secondary care
3. specialist_visit - First appointment with specialist / consultant
4. diagnosis - Cancer confirmed or excluded (histology/MDT)
5. treatment - First definitive treatment started

RULES:
- Each milestone must have an encounter date and encounter_id
- Use the earliest confirmed anchor (referral, diagnosis, or treatment) as your
  timeline starting point -- not all patients are diagnosed via a GP referral
- Patients diagnosed via A&E, secondary care, or hospital admission may have
  NO referral -- use the diagnosis or treatment as the anchor instead
- Treatment may predate GP coding -- do not require treatment > referral date
- Diagnosis must be based on positive evidence (histology, MDT, imaging)
- Treatment must come AFTER diagnosis (for confirmed cases)
- If cancer is excluded, mark status='excluded' with reasoning
- If unsure, mark status='inconclusive' with confidence <70
- Use confidence 0-100 scale

\
"""

EPISODE_BUILDER_TASK_V1 = """\
Build the cancer episode for patient {patient_id}.

Episode entry point:
- Episode ID: {episode_id}
- Cancer type: {condition_type}
- Entry type: {anchor_type}
- Entry date: {anchor_date}

--- Coded data and encounter evidence ---
{coded_summary}

--- Instructions ---
The coded data above includes anchor dates, concept names, sources,
and text snippets from the encounters. Use this evidence to determine:

1. Was cancer CONFIRMED? Look for diagnosis anchors with dates.
   If a diagnosis anchor exists with text like "biopsy confirmed...",
   "histology shows...", or "diagnosed with...", set status=confirmed
   and diagnosis_date to that encounter's date.

   IMPORTANT: Diagnosis can also be INFERRED when there is no explicit
   "diagnosed with" text. If the patient received cancer-specific
   treatment (chemotherapy, radiotherapy, nephrostomy for tumour,
   palliative/hospice care for cancer), or if secondary care letters
   reference a confirmed malignancy, mass, or tumour, then cancer IS
   confirmed. Set diagnosis_date to the earliest encounter where the
   diagnosis became evident (e.g. histology report received, imaging
   showing mass, or the encounter where treatment began).

2. Was cancer EXCLUDED? Look for referral outcome concepts like
   "No evidence of cancer", "Biopsy result normal", "NAD".
   If the only outcome evidence is negative, set status=excluded.

3. Was treatment started? Look for treatment anchors with dates.
   Cancer drug prescriptions (Tamoxifen, Letrozole, etc.) count
   as treatment evidence. Set treatment_date to the earliest.

4. If the evidence is ambiguous or missing, set status=inconclusive
   with a confidence reflecting how much evidence exists.

\
"""

EPISODE_CONSOLIDATION_SYSTEM_V1 = """\
CRITICAL INSTRUCTION: Your entire response must be a single valid JSON object.
Do not write any text, explanation, or markdown before or after the JSON.
Start your response with { and end with }.

You are reviewing multiple cancer episodes that were detected for the same
patient within a short time window. Your task is to decide whether these
episodes represent a SINGLE cancer journey or genuinely separate cancers.

CONTEXT:
In the UK NHS, a patient may receive multiple fast-track referrals in quick
succession to different specialties (e.g. urology, lower GI, haematology)
as part of investigating the SAME underlying cancer. Each referral generates
a separate episode, but they are often part of ONE diagnostic journey.

INDICATORS OF A SINGLE JOURNEY:
- Referrals within 30 days of each other
- Agent reasoning mentions related symptoms, investigations, or treatments
- One specialty refers onward to another (e.g. urologist to oncologist)
- Treatment in one episode is palliative care for condition found in another
- Same anatomical area or related organ systems
- Imaging/investigation results shared across referral pathways

INDICATORS OF SEPARATE CANCERS:
- Clearly different anatomical sites with no connection (e.g. skin + brain)
- Independent diagnosis dates months apart
- Different treatment regimens with no overlap
- Agent reasoning describes unrelated conditions

CHOOSING THE PRIMARY EPISODE:
Do NOT simply pick the episode with the highest confidence score. Instead,
determine which episode represents the ACTUAL cancer site based on clinical
evidence. For example:
- If a positive FIT triggered a lower GI referral, but imaging then found a
  RENAL mass which became the focus of treatment, the urological episode is
  the primary -- the lower GI pathway was a red herring or screening finding.
- If treatment (nephrostomy, palliative care, chemotherapy) targets a specific
  organ, that organ's episode is the primary.
- If one referral leads to another (e.g. urology liaised with haematology to
  exclude lymphoma), the originating specialty is primary.

\
"""

EPISODE_CONSOLIDATION_TASK_V1 = """\
Patient {patient_id} has {episode_count} episodes created within {window_days} days.
Decide whether these are a single cancer journey or separate cancers.

--- Episode summaries ---
{episode_summaries}

--- Instructions ---
Review each episode's cancer type, status, confidence, referral date,
and agent reasoning. Determine:

1. Are these referrals investigating the SAME underlying cancer?
   (e.g. urological referral + lower GI referral for the same tumour)
2. Does the timeline suggest a single diagnostic pathway?
3. Does one episode's reasoning reference findings from another?
4. Which episode represents the ACTUAL cancer site? Look at what was
   found on imaging, what treatment was given, and which specialty
   ultimately managed the patient. Do NOT assume the first or highest-
   confidence episode is the primary -- a screening test (e.g. FIT) may
   trigger a referral that turns out negative while the real cancer is
   found elsewhere.

\
"""
