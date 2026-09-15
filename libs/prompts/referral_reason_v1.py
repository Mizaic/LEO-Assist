"""Focused prompt for extracting the clinical reason for referral.

Atlas trace:
  DI: DI-1B3B5375
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-1B3B5375")

Used by the referral_reason_requested durable step to produce a short
plain-English statement of why the patient is being referred. The result
is written to ReferralRequest.reason so the SBAR Situation prompt can cite
it without needing to search chunk text itself.

Output schema: {"reason": "<single sentence, 10-40 words>"}
"""

from libs.llm_client.prompt_safety import INJECTION_GUARD

REFERRAL_REASON_SYSTEM_V1 = (
    INJECTION_GUARD
    + """\
Objective:
Extract the clinical reason for referral from NHS eRS referral form text.

Scope:
The text may be inside a markdown table cell (| ... |). Ignore table
formatting characters. Ignore the section label itself (e.g. "The reason I am
concerned this patient has cancer is:") and extract only the clinical content
that follows.

Hard requirements:
1. Return a single plain English sentence of 10-40 words.
2. State the presenting symptom(s) or clinical concern that prompted the referral.
3. Do not include the patient name, NHS number, or date of birth.
4. Do not include pathway labels ("2WW", "suspected cancer pathway") unless
   there is no symptom or finding present.
5. If multiple symptoms are present, name the most clinically significant first.
6. If investigation results are present (e.g. FIT negative), include them after
the symptoms.
7. British English spelling.
8. If the text has both an older imaging request note and a later referral
letter, use the referral letter. Do not use a scan-report
"Clinical Information:" line as the reason for referral.

Output contract:
Return ONLY {"reason": "<single sentence>"}. Do not add prose, markdown, code
fences, or additional keys.
"""
)
