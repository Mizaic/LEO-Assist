"""Document-level extraction quality score (not language-model self-rating).

Atlas trace:
  DI: DI-0C766F85
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-0C766F85")
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

from libs.ner.form_checkbox_normalizer import (
    NON_EXTRACTABLE_MARKER,
    extractable_clinical_lines,
    normalize_form_checkbox_text,
)

_SECTION = re.compile(r"(?i)^\s*(section\s+[a-z]|appendix\s+[a-z]|referral criteria)")
_BOX = re.compile(r"\[(?:X|x|\s*)\]")
_DIGITS = re.compile(r"\b\d[\d\s./-]{3,}\b")
_WRAPPER = re.compile(
    r"(?i)(no information provided|see attachment|clinical information summary)"
)
_FORMISH = re.compile(r"(?i)(\[|please put|please take|section [a-z]|appendix )")

FEW_SHOT_OOD_THRESHOLD = 0.45


@dataclass(frozen=True)
class DocumentQuality:
    document_quality_score: float
    quality_reasons: list[str] = field(default_factory=list)
    form_fingerprint_id: str = "unknown"
    few_shot_max_similarity: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


_DOC_HEADER = re.compile(r"(?im)^-{3}\s*document:\s*(?P<name>[^\n]*?)\s*-{3}\s*$")


def primary_document_text(text: str) -> str:
    """Return the bundle without its PDF attachment sections.

    A referral bundle is the GP's form followed by e-RS attachments such as
    "Clinical Information.pdf". The attachment is not part of the printed
    form and its boilerplate ("Clinical Information Summary", "No
    Information Provided") differs between referrals of the same form, so
    judging the form must not read it.

    Deliberately NOT applied to ``form_fingerprint``: that hash keys taught
    :FormSchema lookups in production, and attachment lines already fail
    its section/checkbox filter, so changing it would risk unbinding a
    taught form for no gain.
    """
    source = text or ""
    headers = list(_DOC_HEADER.finditer(source))
    if not headers:
        return source
    kept: list[str] = []
    if headers[0].start() > 0:
        kept.append(source[: headers[0].start()])
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(source)
        name = (header.group("name") or "").strip().lower()
        if name.endswith(".pdf"):
            continue
        kept.append(source[header.start() : end])  # noqa: E203
    return "".join(kept).strip()


def form_fingerprint(text: str) -> str:
    """Hash section titles and checkbox labels with patient values stripped."""
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        skeleton = _BOX.sub("[]", line)
        skeleton = _DIGITS.sub("", skeleton)
        skeleton = re.sub(r"\s+", " ", skeleton).strip().lower()
        if not skeleton:
            continue
        if _SECTION.search(skeleton) or "[]" in skeleton or "please " in skeleton:
            lines.append(skeleton)
    payload = "\n".join(sorted(set(lines)))
    if not payload:
        payload = re.sub(r"\s+", " ", (text or "").lower())[:400]
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _rule_coverage(text: str) -> float:
    raw_lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    form_lines = [ln for ln in raw_lines if _FORMISH.search(ln) or _BOX.search(ln)]
    if not form_lines:
        return 1.0
    normalised = normalize_form_checkbox_text(text)
    classified = 0
    for line in form_lines:
        marked = NON_EXTRACTABLE_MARKER in line or any(
            NON_EXTRACTABLE_MARKER in nln and line[:12] in nln
            for nln in normalised.splitlines()
        )
        if marked:
            classified += 1
            continue
        extractable = extractable_clinical_lines(line)
        if extractable != [line.strip()] or NON_EXTRACTABLE_MARKER in normalised:
            classified += 1
    return classified / len(form_lines)


def _match_fingerprint(fp: str, known: dict[str, str]) -> str:
    for name, stored in (known or {}).items():
        if stored == fp:
            return name
    return "unknown"


def score_document_quality(
    text: str,
    *,
    few_shot_max_similarity: float | None,
    known_fingerprints: dict[str, str] | None = None,
    known_schema: bool = False,
    llm_confidence: float | None = None,
) -> DocumentQuality:
    """Score a document. ``llm_confidence`` is accepted and ignored.

    When ``known_schema`` is ``True`` the form has a saved :FormSchema in
    Neo4j. The gate is bypassed and ``document_quality_score`` is 1.0 so
    the pipeline never pauses on a taught form.

    When ``few_shot_max_similarity`` is ``None`` the route does not use
    retrieval-augmented few-shot selection (for example the NER route).
    The 0.4 weight is redistributed across fingerprint and coverage, and
    ``few_shot_ood`` is never emitted.
    """
    _ = llm_confidence
    if known_schema:
        return DocumentQuality(
            document_quality_score=1.0,
            quality_reasons=[],
            form_fingerprint_id=form_fingerprint(text),
        )
    fp = form_fingerprint(text)
    match_id = _match_fingerprint(fp, known_fingerprints or {})
    primary = primary_document_text(text)
    coverage = _rule_coverage(primary)
    wrapper = 1.0 if _WRAPPER.search(primary) else 0.0
    fp_hit = 1.0 if match_id != "unknown" else 0.0
    reasons: list[str] = []
    if few_shot_max_similarity is None:
        score = max(0.0, min(1.0, 0.5 * fp_hit + 0.5 * coverage - 0.25 * wrapper))
    else:
        few = max(0.0, min(1.0, float(few_shot_max_similarity)))
        score = max(
            0.0,
            min(1.0, 0.4 * few + 0.3 * fp_hit + 0.3 * coverage - 0.25 * wrapper),
        )
        if few < FEW_SHOT_OOD_THRESHOLD:
            reasons.append("few_shot_ood")
    form_like = bool(_FORMISH.search(text or "") or _BOX.search(text or ""))
    if form_like and match_id == "unknown":
        reasons.append("unknown_form_template")
    if coverage < 0.6:
        reasons.append("low_rule_coverage")
    if wrapper:
        reasons.append("wrapper_admin_only")
    return DocumentQuality(
        document_quality_score=round(score, 4),
        quality_reasons=reasons,
        form_fingerprint_id=match_id,
        few_shot_max_similarity=few_shot_max_similarity,
    )
