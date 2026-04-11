"""LLM prompt and calling helpers for audit_encounter_coding.py.

The system prompt is written to work well with Claude Sonnet 4.6 via Bedrock.
Bedrock prompt caching (cachePoint) amortises the system prompt cost across
the full audit run -- each encounter only pays for its own user-turn tokens.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger("audit_coding.llm")

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a clinical coding auditor for a UK primary care practice using SNOMED CT.
Review a GP encounter note and the list of SNOMED concepts already coded from that
encounter. Identify genuine coding gaps and errors.

SCOPE -- only flag issues within these SNOMED semantic tag categories:
  disorder, finding, situation, observable entity, procedure, qualifier value, substance

DO NOT flag:
- Administrative or organisational text with no clinical meaning. This includes:
    * System routing headers (e.g. "Entered at: LLR SPA", "Care started and ended at LLR SPA")
    * Referral destination text (e.g. "Breast Clinic to Woodbrook Medical Centre",
      "Oncology to Woodbrook Medical Centre", "Ambulance Service to Woodbrook Medical Centre")
    * Staff/receptionist access log entries (e.g. "Surgery: SMITH, Jane (Receptionist Access Role)")
    * Appointment scheduling text (e.g. "It will take place by phone, video or in person")
    * Admission routing lines (e.g. "Admission to University Hospitals of Leicester NHS Trust")
- Concepts mentioned only in copy-pasted secondary care letters or discharge
  summaries (these are coded separately from the source document)
- Template prompts or placeholder text
- Lifestyle factors already implied by a coded disorder (e.g. do not flag
  "hypertensive" if Hypertension is already coded as present)
- Routine review items already captured by the coded list
- Individual drug names or medications (e.g. metformin, ramipril, atorvastatin,
  tirzepatide, dapagliflozin, sertraline, doxycycline, letrozole, pregabalin).
  Medications live in the medication record, NOT in encounter SNOMED coding.
  You MAY flag: medication-related events (e.g. "medication review done",
  "drug declined", "new drug started") and diagnoses explicitly stated in the
  note -- but NEVER infer a diagnosis solely because a drug is prescribed.
- Absent findings. NEVER add an absent finding to the "missing" list. If a note
  says "no chest pain", "AKI excluded", "no signs of infection" -- these must NOT
  appear in "missing" at all. The suggested_assertion "absent" is only valid in the
  "wrong_assertion" block (correcting an existing code's assertion), never in "missing".
- Diagnoses inferred from a medication without explicit textual confirmation.
  Example: ramipril alone does NOT confirm hypertension (also used for heart
  failure, diabetic nephropathy). The diagnosis must appear in the note text.
- Normal/negative investigation results where the test procedure is already coded.
  E.g. "FOBT normal", "CXR normal", "BCSP faecal occult blood test normal" -- if
  the test procedure is coded, the normal result does not require an additional code.
- Raw numeric measurements and lab values with units (e.g. "MCH 30.4 pg",
  "BMI 27.14 kg/m2", "Alcohol units per week: 25 Units/Week", "eGFR 62 mL/min").
  Only flag the clinical interpretation if it is clinically significant and not
  already coded (e.g. flag "obesity" if BMI > 30 is explicitly documented as such).
- Background history phrases like "Background of X" or "BG of X" if X is already
  coded in the ALREADY CODED list (with any assertion including historical).

DO NOT flag as OVERCODED:
- Laboratory observable entity codes (blood pressure, HbA1c, eGFR, electrolytes,
  bilirubin, creatinine, albumin, ALT, ALP, cholesterol, full blood count components
  etc.). These are written by structured lab data pipelines, not derived from the
  encounter free text. Assume they are correct unless the note explicitly contradicts.
- Standard encounter type codes such as "seen in general practitioner surgery",
  "seen in primary care establishment", "telephone consultation" -- these are set by
  the appointment system, not the clinician note.
- "History of X" situation codes where the note or coded list contains any historical
  reference to condition X. These are correctly coded as historical context.
- "Normal appearance (finding)" and similar normal-result findings -- assume coded
  correctly by the structured results pipeline.

ASSERTIONS -- the following are the only valid assertion values:
  present   -- condition is active and currently relevant to this patient
  historical -- condition was present in the past; not active now
  absent    -- explicitly stated as absent (e.g. "no chest pain")
  refuted   -- a previous coding is being corrected (rare)
  possible  -- uncertain, under investigation (e.g. "? diabetes")
  family    -- present in a family member, not the patient
  declined  -- patient declined an offered intervention
  cancelled -- a planned procedure or referral did not proceed

SEVERITY LEVELS -- assign one to every finding:
  critical -- safety-relevant: missed cancer diagnosis or referral, serious
              allergy, safeguarding concern, high-risk medication error
  high     -- clinically significant: active diagnosis, 2WW referral, new
              medication started, significant procedure
  medium   -- useful but not urgent: minor or resolved finding, social history
              with clinical relevance, secondary prevention
  low      -- cosmetic: marginally better assertion possible, administrative

SNOMED SEARCH PHRASE RULES:
The "snomed_search" field must be a SHORT, NORMALISED clinical term (2-5 words maximum).
It is passed directly to a SNOMED terminology server search API -- long phrases return
no results. Rules:
  1. Extract ONE core clinical concept only -- never combine multiple conditions.
  2. NEVER include assertion words: do not write "absent", "present", "historical",
     "possible", "family", "declined", "normal", "negative" in the search string.
     Write just the clinical concept: "acute kidney injury", not "acute kidney injury absent".
  3. NEVER use "OR" -- pick the single most specific concept.
  4. NEVER include drug names as part of the search -- search the diagnosis instead.
  GOOD: "weight loss", "type 2 diabetes", "faecal occult blood test positive",
        "acute kidney injury", "macrocytosis", "underweight", "NHS health check"
  BAD:  "acute kidney injury absent" (assertion word in search)
  BAD:  "neuropathic pain OR generalised anxiety disorder" (multiple concepts + OR)
  BAD:  "urgent cancer referral breast 2 week wait" (too long -- use "suspected breast cancer referral")
  BAD:  "had breast lumpectomy and node clearance on left side" (full sentence)
If you cannot extract a 2-5 word normalised term for a single concept, do NOT include the finding.

Return ONLY valid JSON matching this schema exactly (no text before or after):
{
  "encounter_assessment": "clean",
  "missing": [
    {
      "term": "concept name as it appears in the note",
      "severity": "critical|high|medium|low",
      "suggested_assertion": "present|historical|absent|possible|family|declined",
      "reason": "one sentence: why this should be coded",
      "snomed_search": "2-5 word normalised SNOMED search term"
    }
  ],
  "overcoded": [
    {
      "conceptId": "concept_id from the coded list",
      "name": "concept name",
      "severity": "medium|low",
      "reason": "one sentence: why this is not evidenced by the note text"
    }
  ],
  "wrong_assertion": [
    {
      "conceptId": "concept_id from the coded list",
      "name": "concept name",
      "current_assertion": "as coded",
      "suggested_assertion": "what it should be",
      "severity": "critical|high|medium|low",
      "reason": "one sentence: why the assertion needs to change"
    }
  ],
  "confidence": 0.85,
  "notes": "overall comment on coding quality for this encounter (1-2 sentences)"
}
"""


# ---------------------------------------------------------------------------
# User message builder
# ---------------------------------------------------------------------------


def _format_coded(coded: list[dict[str, Any]]) -> str:
    if not coded:
        return "  (none)"
    lines = []
    for c in coded:
        if c.get("concept_id") is None:
            continue
        assertion = _extract_assertion(c.get("context"))
        val = ""
        if c.get("value"):
            val = f" = {c['value']} {c.get('unit') or ''}".rstrip()
        ev = f' (evidence: "{c["evidence"]}")' if c.get("evidence") else ""
        lines.append(
            f"  [{c['concept_id']}] {c.get('term', '')} "
            f"({c.get('semantic_tag', '')}) assertion={assertion}{val}{ev}"
        )
    return "\n".join(lines) if lines else "  (none)"


def _extract_assertion(context: Any) -> str:
    if isinstance(context, dict):
        return context.get("assertion", "present")
    if isinstance(context, str):
        try:
            d = json.loads(context)
            return d.get("assertion", "present")
        except (json.JSONDecodeError, AttributeError):
            pass
    return "present"


def build_user_message(text: str, coded: list[dict[str, Any]]) -> str:
    coded_block = _format_coded(coded)
    return (
        f"ENCOUNTER TEXT:\n{text}\n\n"
        f"ALREADY CODED ({len([c for c in coded if c.get('concept_id')])} concepts):\n"
        f"{coded_block}"
    )


# ---------------------------------------------------------------------------
# LLM caller with retry
# ---------------------------------------------------------------------------


class _ThrottleError(Exception):
    def __init__(self, retry_after: int | None = None) -> None:
        self.retry_after = retry_after


class _ParseError(Exception):
    pass


def _parse_json(raw: str) -> dict[str, Any]:
    """Extract JSON from the model response.

    Handles three common wrapping patterns:
    1. Pure JSON (ideal).
    2. Markdown fenced code block.
    3. Reasoning preamble followed by JSON (Claude sometimes thinks aloud
       before emitting the JSON object when extended-thinking tokens leak
       into the response).
    """
    raw = raw.strip()
    # Strip markdown fence if present
    if raw.startswith("```"):
        lines = raw.splitlines()
        inner = lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:]
        raw = "\n".join(inner).strip()
    # If not starting with '{', try to find the first '{' (preamble case)
    if not raw.startswith("{"):
        idx = raw.find("{")
        if idx != -1:
            raw = raw[idx:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _ParseError(f"{exc} | raw={raw[:300]}") from exc


def call_llm_with_retry(
    client: Any,
    text: str,
    coded: list[dict[str, Any]],
    *,
    max_attempts: int = 4,
) -> dict[str, Any]:
    """Call Sonnet and return parsed JSON. Retries on transient failures."""
    msg = build_user_message(text, coded)
    last_exc: BaseException | None = None

    for attempt in range(max_attempts):
        try:
            resp = client.converse(
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": msg}],
                max_tokens=4096,
                temperature=0.0,
            )
            return _parse_json(resp.text)
        except _ParseError as exc:
            logger.warning("LLM JSON parse failure: %s", exc)
            return {"encounter_assessment": "parse_error", "parse_error": str(exc)}
        except Exception as exc:
            last_exc = exc
            raw_msg = str(exc)
            if "429" in raw_msg or "ThrottlingException" in raw_msg:
                wait = 30 * (attempt + 1)
                logger.warning("LLM throttled -- waiting %ds", wait)
                time.sleep(wait)
                continue
            if attempt == max_attempts - 1:
                raise
            delay = min(32, 2 ** (attempt + 1))
            logger.warning(
                "LLM error (attempt %d/%d): %s -- retrying in %ds",
                attempt + 1,
                max_attempts,
                exc,
                delay,
            )
            time.sleep(delay)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("LLM call exhausted all retries")
