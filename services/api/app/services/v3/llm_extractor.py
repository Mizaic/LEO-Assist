"""LLM-backed term extraction in 5-sentence batches for V3."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.services.v3.bedrock_retry import converse_with_retry
from app.services.v3.llm_usage import LLMUsage
from app.services.v3.sentence_splitter import SentenceChunk

logger = logging.getLogger(__name__)


class ExtractionError(RuntimeError):
    """Raised when LLM extraction fails and no fallback is permitted."""


_VALID_ASSERTIONS = frozenset(
    {"present", "absent", "possible", "historical", "hypothetical", "family"}
)

_ASSERTION_TO_CONTEXT: dict[str, dict[str, object]] = {
    "present": {
        "negated": False, "uncertain": False, "historical": False,
        "subject": "patient", "temporality": "present",
    },
    "absent": {
        "negated": True, "uncertain": False, "historical": False,
        "subject": "patient", "temporality": "present",
    },
    "possible": {
        "negated": False, "uncertain": True, "historical": False,
        "subject": "patient", "temporality": "hypothetical",
    },
    "historical": {
        "negated": False, "uncertain": False, "historical": True,
        "subject": "patient", "temporality": "past",
    },
    "hypothetical": {
        "negated": False, "uncertain": False, "historical": False,
        "subject": "patient", "temporality": "hypothetical",
    },
    "family": {
        "negated": False, "uncertain": False, "historical": False,
        "subject": "family", "temporality": "unknown",
    },
}

_SYSTEM_PROMPT = """\
You are a UK primary care clinical entity extractor. You identify SNOMED CT-codable \
clinical entities from de-identified GP consultation text.

You will receive the full encounter text for clinical context and a subset of \
sentences to process. Extract entities ONLY from the provided sentence subset. \
Use the encounter text to resolve ambiguity only.

## JSON Output

Return ONLY valid JSON. No explanation, no markdown, no preamble.

{
  "terms": [
    {
      "sentence_id": "s0",
      "text": "exact surface form from the sentence",
      "lookup_term": "standard clinical term for SNOMED lookup",
      "semantic_tag": "disorder",
      "assertion": "present"
    }
  ]
}

Return {"terms": []} when no codable entities exist in the sentence subset.

## Extraction Scope

EXTRACT entities representing clinically codable concepts:
- Disorders: diagnosed conditions, diseases, syndromes, infections
- Findings: symptoms, signs, examination findings, test results
- Procedures: operations, tests, referrals, examinations actually performed
- Substances: medications and drugs as named in the text
- Observable entities: clinically significant parameters with or without values
- Situations: smoking status, family history, allergy status, resolved conditions

DO NOT EXTRACT:
- Non-clinical words: "patient", "reviewed", "discussed", "advised", "today", \
"appointment", "follow-up"
- Body sites without an associated clinical finding: "chest" alone, "left arm" alone
- Parenthetical Read codes such as (G30..) or (H33..) — these are handled by a \
separate pipeline step
- Section labels: "Problem:", "History:", "Medication:", "Examination:", "Comment:"
- Bare numeric values without their clinical parameter: "130/80" alone, "7.2" alone \
(but DO extract when a label is present: "BP: 130/80" or "HR: 73 bpm" are codable)
- Content appearing ONLY in safety-netting or worsening-advice text — these describe \
what might happen, not what is present
- Administrative and workflow entries: "appointment booked", "SMS sent", \
"prescription issued", "adv" (advised), "N/A", "POV" (point of view)
- Orders or requests not yet performed: "blood test requested", "referral made"

## Semantic Tags

Assign exactly one tag from this set. These are the standard SNOMED CT hierarchy tags.

- disorder — Diagnosed diseases, conditions, syndromes. Use when a formal diagnosis \
is stated or implied by the problem list.
- finding — Symptoms, signs, examination results, test results. Use for observations \
that are not yet a formal diagnosis.
- procedure — Clinical actions performed: operations, tests, referrals, examinations, \
therapeutic procedures.
- substance — Medications, drugs, chemical substances by name.
- observable entity — Measurable clinical parameters: blood pressure, BMI, HbA1c, weight.
- situation — Contextualised clinical statements: family history, resolved conditions, \
risk factors, allergy status, smoking status.
- product — Specific pharmaceutical preparations when a brand name or formulation is stated.
- regime/therapy — Named treatment protocols or care plans.

Use "finding" for symptoms and signs. Use "disorder" for anything on a problem list or \
stated as a diagnosis.

## Surface Form Rules

The "text" field is used for character-offset alignment against the source sentence. \
The "lookup_term" field feeds into SNOMED CT terminology resolution.

- "text": Always the exact form as it appears in the sentence. Do not modify, expand, \
or paraphrase.
- "lookup_term": A concise, standard clinical term suitable for SNOMED CT terminology \
lookup. Same as "text" when the source already uses standard clinical wording. \
Keep lookup_term short and natural — use the simplest standard name for the concept. \
Do NOT construct verbose multi-word descriptions. For example: "left shoulder pain" \
not "pain in the left shoulder region", "polio vaccination" not \
"diphtheria, tetanus, pertussis and polio vaccination".

When the source uses a GP abbreviation, keep the abbreviation in "text" and place the \
standard expansion in "lookup_term":
  HTN → hypertension, DM → diabetes mellitus, T2DM → type 2 diabetes mellitus, \
AF → atrial fibrillation, OA → osteoarthritis, CKD → chronic kidney disease, \
COPD (keep as-is — is a recognised SNOMED term), IHD → ischaemic heart disease, \
TIA → transient ischaemic attack, UTI → urinary tract infection, \
LRTI → lower respiratory tract infection, URTI → upper respiratory tract infection, \
SOB → shortness of breath, MI → myocardial infarction, PE → pulmonary embolism, \
DVT → deep vein thrombosis, CCF → congestive cardiac failure, \
NAD → no abnormality detected, O/E → on examination, Hx → history, \
Dx → diagnosis, Rx → prescription, PMH → past medical history, \
FH → family history, SH → social history, FROMS → full range of movements, \
FROM → full range of movement, ROM → range of movement, \
MSU / msu → midstream urine, MC&S / MC+S → microscopy culture and sensitivities, \
KESC → Klebsiella Enterobacter Serratia Citrobacter group, \
NKDA → no known drug allergies, Nitro → nitrofurantoin (antibiotic context), \
HR → pulse rate, RR → respiratory rate, Temp → body temperature, \
BP → blood pressure, SpO2 / sats / O2 sats → oxygen saturation, \
BMI → body mass index, GCS → Glasgow Coma Scale, \
NEWS / NEWS2 → National Early Warning Score, \
Wt → body weight, Ht → height.

When the text contains a vital-signs line with a shorthand label, a value, and a unit \
(e.g. "HR: 73 bpm", "BP: 142 / 92", "Temp: 36.4 C", "RR: 17 breath/min"), \
extract the parameter as an observable entity with the shorthand in "text" and the \
standard clinical term in "lookup_term". Include the numeric value and unit in the \
lookup_term context: e.g. text="HR" lookup_term="pulse rate" semantic_tag="observable entity".\


When the source uses a pharmaceutical brand name, keep the brand name in "text" and \
place the generic active ingredient in "lookup_term". Common examples: \
Zomorph → morphine, Amoxil → amoxicillin, Augmentin → co-amoxiclav, \
Losec → omeprazole, Gaviscon → alginate compound, Ventolin → salbutamol, \
Seretide → fluticasone/salmeterol, Lantus → insulin glargine.

For drug + formulation mentions (e.g., "Nitrofurantoin 100mg modified-release capsules"), \
use only the drug name as lookup_term: "nitrofurantoin".

When the surface text describes a clinical action in informal terms, use the standard \
clinical procedure name in lookup_term: \
"nephrostomy flush" → "nephrostomy irrigation", \
"urine sample for MC&S" → "urine microscopy culture and sensitivities", \
"blood test" → "blood test".

Extract the complete clinical concept, not a fragment. "Type 2 diabetes mellitus" \
not "diabetes". "Mixed anxiety and depressive disorder" not "anxiety".

Each distinct concept once per sentence only.

## Assertion Classification

Classify each entity's clinical status. Use linguistic cues from the sentence to \
determine assertion. Default to "present" when no modifying cues exist.

present — Confirmed, currently active for this patient.

absent — Explicitly negated.
  Cues: "no", "nil", "denies", "without", "negative for", "ruled out", "excluded", \
"not found", "not present", "absent", "never had", "no evidence of", "free of", \
"clear of".
  CRITICAL: When a sentence opens with "No", "Nil", "Denies", or "Reports no", \
EVERY clinical entity in that sentence is absent — not just the first one.
  Example: "No bloating, change in bowel habit, or rectal bleeding" — all three \
entities are absent.

possible — Uncertain or suspected.
  Cues: "?", "query", "suspected", "possible", "probable", "likely", "concerning for", \
"differential includes", "under investigation", "to be excluded", \
"awaiting confirmation".

historical — Past condition, no longer active.
  Cues: "history of", "Hx of", "previous", "resolved", "cleared", "settled", \
"has since resolved", "no longer present", "had X but now resolved", "went after", \
"has stopped", "cleared up", "no longer".
  When a sentence describes a past event using cues like "went after", "has stopped", \
"cleared up", the related findings should be classified as "historical".

hypothetical — Conditional or planned, not currently present.
  Cues: "if develops", "should symptoms worsen", "consider if", "risk of developing", \
"plan to".
  CRITICAL: Do NOT extract entities from safety-netting or worsening-advice phrases. \
"If the pain becomes severe or is associated with shortness of breath, seek urgent \
review" — shortness of breath is NOT present and should NOT be extracted. If you must \
include it, use assertion "hypothetical".

family — Pertains to a family member, not the patient.
  Cues: "FH:", "family history of", "mother had", "father had", \
"sibling diagnosed with", "runs in the family", "familial".

Before finalising each entity, re-read the source sentence and confirm: does the text \
assert this entity IS present for this patient right now? If not, assign the correct \
non-present assertion or omit the entity.

## Constraints

1. Every "text" value must consist of words found in the source sentence. Do not \
fabricate terms.
2. An empty result {"terms": []} is correct and expected when sentences contain no \
codable content.
3. Do not extract the same concept twice from one sentence, even if mentioned in \
different words.\
"""


@dataclass(frozen=True)
class ExtractedTerm:
    sentence_id: str
    text: str
    lookup_term: str
    semantic_tag: str
    assertion: str
    context: dict[str, Any]
    modifiers: dict[str, Any]


def _extract_bedrock_text(response: dict[str, Any]) -> str:
    content = response.get("output", {}).get("message", {}).get("content", [])
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and "text" in item:
            parts.append(str(item["text"]))
    return "\n".join(parts).strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def assertion_to_context(assertion: str) -> dict[str, object]:
    """Map a unified assertion label to the legacy context dict."""
    return dict(_ASSERTION_TO_CONTEXT.get(assertion, _ASSERTION_TO_CONTEXT["present"]))


class LLMExtractor:
    def __init__(self, *, model_id: str, region: str | None = None) -> None:
        self.model_id = model_id
        self.region = region
        self._client = self._init_client(region)

    @staticmethod
    def _init_client(region: str | None):
        try:
            import boto3  # pylint: disable=import-outside-toplevel
        except Exception:  # pragma: no cover
            return None
        try:
            return boto3.client("bedrock-runtime", region_name=region)
        except Exception:  # pragma: no cover
            return None

    @property
    def enabled(self) -> bool:
        return bool(self._client and self.model_id and self.model_id != "unconfigured")

    def extract_batch(
        self,
        encounter_text: str,
        sentences: list[SentenceChunk],
    ) -> tuple[list[ExtractedTerm], LLMUsage]:
        if not sentences:
            return [], LLMUsage.zero()
        if not self.enabled:
            raise ExtractionError(
                "LLM extractor is not enabled (model_id=%s)" % self.model_id
            )

        sids = [s.sentence_id for s in sentences]
        logger.info("Sending %d sentences to LLM (%s)", len(sentences), sids)
        user_prompt = self._build_user_prompt(encounter_text, sentences)
        try:
            response = converse_with_retry(
                self._client,
                model_id=self.model_id,
                system=[{"text": _SYSTEM_PROMPT}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                inferenceConfig={"maxTokens": 2048, "temperature": 0.0},
            )
        except Exception as exc:
            raise ExtractionError("LLM converse() call failed: %s" % exc) from exc

        batch_usage = LLMUsage.from_bedrock_response(response)
        logger.info(
            "LLM response received - %d in / %d out tokens (cached=%d), stop=%s",
            batch_usage.input_tokens,
            batch_usage.output_tokens,
            batch_usage.cached_input_tokens,
            response.get("stopReason", "?"),
        )
        raw_text = _extract_bedrock_text(response)
        parsed = _parse_json_object(raw_text)
        if not parsed:
            raise ExtractionError(
                "LLM returned unparseable response for sentences %s: %s"
                % (sids, raw_text[:200])
            )
        terms = self._parse_terms(parsed, sentences)
        logger.info("Parsed %d terms from LLM response", len(terms))
        return terms, batch_usage

    @staticmethod
    def _build_user_prompt(
        encounter_text: str, sentences: list[SentenceChunk],
    ) -> str:
        sentence_payload = [
            {"sentence_id": s.sentence_id, "text": s.text}
            for s in sentences
        ]
        return (
            "Extract clinical entities from the sentence subset below.\n"
            "The encounter text provides clinical context only - "
            "extract from the sentences.\n\n"
            f"Encounter text:\n{encounter_text}\n\n"
            f"Sentences:\n{json.dumps(sentence_payload, ensure_ascii=False)}"
        )

    def _parse_terms(
        self,
        payload: dict[str, Any],
        sentences: list[SentenceChunk],
    ) -> list[ExtractedTerm]:
        valid_ids = {s.sentence_id for s in sentences}
        raw_terms = payload.get("terms", [])
        out: list[ExtractedTerm] = []
        dropped = 0
        for row in raw_terms:
            if not isinstance(row, dict):
                dropped += 1
                continue
            sid = str(row.get("sentence_id", "")).strip()
            text = str(row.get("text", "")).strip()
            if not sid or sid not in valid_ids or not text:
                dropped += 1
                continue

            lookup_term = str(row.get("lookup_term", text)).strip() or text
            semantic_tag = str(row.get("semantic_tag", "finding")).strip() or "finding"
            assertion = str(row.get("assertion", "present")).strip().lower()
            if assertion not in _VALID_ASSERTIONS:
                logger.warning(
                    "Invalid assertion %r for text=%r - defaulting to 'present'",
                    assertion, text,
                )
                assertion = "present"

            context = assertion_to_context(assertion)
            out.append(
                ExtractedTerm(
                    sentence_id=sid,
                    text=text,
                    lookup_term=lookup_term,
                    semantic_tag=semantic_tag,
                    assertion=assertion,
                    context=context,
                    modifiers={},
                )
            )
        if dropped:
            logger.warning("Dropped %d/%d rows from LLM response (bad sid or empty text)", dropped, len(raw_terms))
        return out

