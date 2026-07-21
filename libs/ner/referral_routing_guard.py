"""Suppress informational 2WW / referral routing spans from extraction output.

Atlas trace:
  DI: DI-B5C78811, DI-1B3B5375, DI-95CB940F
  DO: DO-728930A1, DO-847F1ED5
  UN: UN-89E2AE36

UK referral templates often repeat pathway labels (2WW submitted, refer under
pathway) that are true in the document but are not phrase-level clinical facts.
Named tests, symptoms, and site-named suspected-cancer situations must be kept.
Pure transport (referral placed/submitted, e-Referral) remains dropped.
"""

from __future__ import annotations

import re

# Named investigations / results -- if present, the span is clinical not routing.
_NAMED_TEST_RE = re.compile(
    r"\b(?:"
    r"MRI|CT\s|CT\b|colonoscopy|gastroscopy|bronchoscopy|cystoscopy|"
    r"ultrasound|USS|CXR|chest\s+x-?ray|x-?ray|"
    r"FIT[\+\-]|FIT\s*[\+\-]|FIT\s*positive|FIT\s*negative|"
    r"CA\s*125|CA125|PSA|TSH|HbA1c|"
    r"faecal\s+immunochemical|immunochemical\s+test|"
    r"endoscopy|biopsy|mammogram|smear"
    r")\b",
    re.IGNORECASE,
)

# Clinical actions that mention referral but are not pure routing.
_KEEP_ACTION_RE = re.compile(
    r"\b(?:"
    r"patient\s+declined\s+referral|declined\s+referral|"
    r"(?:MRI|colonoscopy|CT|ultrasound|gastroscopy|bronchoscopy)"
    r"\s+.{0,40}\b(?:arranged|booked|ordered)|"
    r"(?:arranged|booked|ordered)"
    r".{0,40}\b(?:MRI|colonoscopy|CT|ultrasound)\b|"
    r"urgent\s+MRI\s+scan\s+of\s+the\s+brain|"
    r"MRI\s+scan\s+of\s+the\s+brain\s+has\s+been\s+arranged"
    r")\b",
    re.IGNORECASE,
)

_SITE = (
    r"(?:breast|lung|skin|prostate|ovarian|ovary|cervix|cervical|endometrial|"
    r"colorectal|bowel|stomach|gastric|oesophageal|esophageal|pancreatic|"
    r"pancreas|liver|bladder|kidney|renal|testis|testicular|brain|cns|"
    r"lymphoma|leukaemia|leukemia|myeloma|sarcoma|"
    r"head\s+and\s+(?:or\s+)?neck|lower\s+gi|upper\s+gi|"
    r"upper\s+gastrointestinal|lower\s+gastrointestinal|"
    r"urolog(?:y|ical)|gynaecolog(?:y|ical)|gynecolog(?:y|ical)|"
    r"haematolog(?:y|ical)|hematolog(?:y|ical))"
)

# Site / organ-system cancer suspicion -- keep as clinical situation content.
_CLINICAL_SUSPICION_RE = re.compile(
    rf"\b(?:"
    rf"suspected\s+{_SITE}\s+cancer\b|"
    rf"{_SITE}\s+suspected\s+cancer\b|"
    rf"suspected\s+(?:cancer\s+pathway\s+for\s+)?{_SITE}\s+cancer\b|"
    rf"(?:cancer\s+pathway\s+for\s+){_SITE}\s+cancer\b|"
    rf"(?:gastric|stomach|oesophageal|esophageal|colorectal|pancreatic|"
    rf"breast|lung|skin|prostate)\s+malignancy\b|"
    rf"malignant\s+neoplasm\s+of\s+.+\s+suspected\b|"
    rf".+\s+cancer\s+suspected\b"
    rf")",
    re.IGNORECASE,
)

_ROUTING_2WW_RE = re.compile(
    r"\b(?:urgent\s+)?(?:2\s*ww|two\s+week\s+wait|fast\s+track)\b",
    re.IGNORECASE,
)

# Pure transport / form plumbing -- not clinical suspicion.
_REFERRAL_ROUTING_RE = re.compile(
    r"\b(?:"
    r"referral\s+(?:placed|submitted|sent|complete|completed)|"
    r"referral\s+placed|"
    r"e-?referral|"
    r"2ww\s+.+\s+referral\s+(?:placed|submitted|sent)?|"
    r"(?:2\s*ww|two\s+week\s+wait|fast\s+track)\s+.+\s+referral\s+"
    r"(?:placed|submitted|sent)\b|"
    r"urgent\s+(?:2\s*ww|two\s+week\s+wait)\s+.+\s+referral\s+for\b|"
    r"(?:urgent\s+)?(?:2\s*ww|two-?week\s+wait|fast\s+track)\s+pathway\b"
    r")",
    re.IGNORECASE,
)

_GENERIC_REFERRAL_ONLY_RE = re.compile(
    r"^(?:"
    r"(?:urgent\s+)?(?:2\s*ww|two-?week\s+wait|fast\s+track)\s+(?:.+?\s+)?"
    r"(?:referral|pathway)\b|"
    r".+?\s+referral\s+(?:placed|submitted)\b|"
    r"refer\s+this\s+patient\b(?!\s+under\s+the\s+.+\s+cancer)"
    r")\.?$",
    re.IGNORECASE,
)

# Transport-only "refer under pathway" with no site-named clinical suspicion.
_TRANSPORT_REFER_UNDER_RE = re.compile(
    r"\b(?:refer\s+this\s+patient\s+under\s+the|referred\s+under\s+the)\b",
    re.IGNORECASE,
)


def should_keep_referral_span(text: str) -> bool:
    """Return True when a span must not be dropped as routing noise."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    if _NAMED_TEST_RE.search(stripped):
        return True
    if _KEEP_ACTION_RE.search(stripped):
        return True
    if _CLINICAL_SUSPICION_RE.search(stripped):
        return True
    return False


def is_informational_referral_routing(text: str) -> bool:
    """Return True when the span is 2WW/pathway routing without a clinical fact."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    if should_keep_referral_span(stripped):
        return False

    if _REFERRAL_ROUTING_RE.search(stripped):
        return True

    if _TRANSPORT_REFER_UNDER_RE.search(stripped):
        return True

    if _ROUTING_2WW_RE.search(stripped) and re.search(
        r"\breferral\b", stripped, re.IGNORECASE
    ):
        return True

    if _GENERIC_REFERRAL_ONLY_RE.match(stripped):
        return True

    # Short pathway labels without symptoms or test names.
    if re.search(r"\b2ww\b", stripped, re.IGNORECASE) and len(stripped) < 80:
        if not re.search(
            r"\b(?:weakness|pain|bleeding|lump|mass|disturbance|scan|MRI|FIT)\b",
            stripped,
            re.IGNORECASE,
        ):
            return True

    return False


def should_suppress_referral_routing_entity(entity: dict) -> bool:
    """Return True when an entity dict should be dropped as routing noise."""
    text = str(
        entity.get("text")
        or entity.get("normalized")
        or entity.get("normalized_lookup")
        or entity.get("lookup_term")
        or ""
    )
    return is_informational_referral_routing(text)
