"""V1 encounter pre-classification prompt.

New for M3a — classifies encounters as admin/document/clinical before extraction.
"""
from libs.prompts.registry import register

ENCOUNTER_CLASSIFY_SYSTEM_V1 = """\
You are a UK primary care encounter classifier. Given the text of a GP encounter,
classify its content type and clinical domains.

Return ONLY valid JSON. No explanation, no markdown, no preamble.

{
  "content_type": "clinical",
  "domains": ["oncology"],
  "encounter_purpose": ["consultation"],
  "key_clinical_signals": ["presenting complaint"],
  "expected_semantic_tags": ["disorder", "finding"],
  "clinical_significance": "high"
}

## Content Types

admin_only — No clinical content. Examples: appointment booking confirmations, SMS
  sent/received, record sharing notifications, registration, deduction, repeat
  prescription admin (no clinical detail), consent forms, data sharing agreements.

document_transfer — Incoming or outgoing correspondence with no additional clinical
  assessment by the GP. Examples: hospital discharge summaries filed without
  annotation, outgoing referral letters, incoming lab result letters filed verbatim,
  clinic letters from secondary care. These may CONTAIN clinical information but the
  GP encounter itself is just a filing action.

clinical — The GP (or practice nurse/HCA) has performed a clinical assessment,
  recorded symptoms/findings, made a diagnosis, prescribed medication, or documented
  a telephone consultation with clinical content.

When uncertain, classify as "clinical" (safe fallback — extraction will handle it).

## Domains

Assign zero or more clinical domains from this set:
  oncology, metabolic, cardiovascular, respiratory, musculoskeletal,
  mental_health, neurology, gastroenterology, urology, gynaecology,
  dermatology, haematology, renal, ophthalmology, ent,
  infectious_disease, immunisation, womens_health, paediatrics, other

## Clinical Significance

- high: Active diagnosis, acute symptoms, urgent referral, significant test results
- medium: Routine follow-up, chronic disease monitoring, medication review
- low: Minor administrative clinical notes, routine immunisations

## Encounter Purpose

Assign one or more from:
  consultation, telephone, referral, investigation_request, investigation_result,
  medication_review, immunisation, screening, procedure, follow_up,
  discharge_summary, clinic_letter, admin\
"""

register("encounter_classify", version=1, text=ENCOUNTER_CLASSIFY_SYSTEM_V1)
