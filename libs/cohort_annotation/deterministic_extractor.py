"""Deterministic lab and vitals span extractor.

Wraps libs.training.lab_span_detector.detect_lab_pattern to produce
annotation-ready entity dicts for every sentence that matches the
lab/vitals pattern. This is the first extraction step; the LLM
StructuredVerify node only has to fill the gaps.

Output entities use the same schema as the LLM annotator nodes:
    {
        "id":          "d1",   # prefix "d" = deterministic
        "sentence_id": int,
        "quote":       str,    # verbatim from sentence text
        "labels":      [str],
        "assertion":   str,
        "rationale":   str,    # always "deterministic R1/R8"
        "source":      "deterministic",
    }
"""

from __future__ import annotations

import re
from typing import Any

from libs.training.lab_span_detector import detect_lab_pattern

# BMI / vitals patterns that don't carry a Read code but still produce
# nested spans when accompanied by a numeric value.
_VITALS_PROCEDURE_RE = re.compile(
    r"(?P<name>"
    r"(?:blood\s+pressure\s+reading|blood\s+pressure|pulse\s+rate|heart\s+rate"
    r"|respiratory\s+rate|oxygen\s+saturation|body\s+mass\s+index\s+-\s+observation"
    r"|body\s+mass\s+index|temperature|weight|height|BMI)"
    r"(?:\s*\([A-Za-z0-9.]{3,8}\))?)"   # optional Read code
    r"\s+(?P<rest>[^\n]{3,80})",          # value + optional unit + interpretation
    re.IGNORECASE,
)

_VITALS_VALUE_RE = re.compile(r"\d[\d./]{0,6}")

_VITALS_INTERP_RE = re.compile(
    r"[-–]\s*(?:above\s+reference\s+range|outside\s+reference\s+range"
    r"|below\s+reference\s+range|overweight|obese|underweight|normal"
    r"|hypertensive|raised|elevated|low)",
    re.IGNORECASE,
)


def _normalise_id(prefix: str, idx: int) -> str:
    return f"{prefix}{idx}"


def _extract_vitals(
    sentence_text: str,
    sentence_id: int,
    id_offset: int,
) -> list[dict[str, Any]]:
    """Extract nested vitals spans (R8) for non-coded BP/weight/BMI lines."""
    entities: list[dict[str, Any]] = []
    idx = id_offset

    for m in _VITALS_PROCEDURE_RE.finditer(sentence_text):
        name = m.group("name").strip()
        rest = m.group("rest")

        # Find where the procedure name ends (start is always name_start)
        name_start = m.start()
        name_end = name_start + len(name)

        # Does it have a numeric value?
        val_m = _VITALS_VALUE_RE.search(rest)
        if not val_m:
            # Name-only: one PROCEDURE span
            entities.append({
                "id":          _normalise_id("d", idx),
                "sentence_id": sentence_id,
                "quote":       sentence_text[name_start:name_end],
                "labels":      ["PROCEDURE"],
                "assertion":   "present",
                "rationale":   "deterministic R8 vitals name-only",
                "source":      "deterministic",
            })
            idx += 1
            continue

        # Measure how far the value + unit extend
        rest_val_end = val_m.end()
        # Extend to include unit token immediately after value
        unit_m = re.match(r"\s*[A-Za-z/%^]{1,10}", rest[rest_val_end:])
        if unit_m:
            rest_val_end += unit_m.end()
        # Include reference range [...]
        range_m = re.match(r"\s*\[[^\]]{1,40}\]", rest[rest_val_end:])
        if range_m:
            rest_val_end += range_m.end()

        obs_end = m.start("rest") + rest_val_end

        # Does it have an interpretation phrase?
        interp_m = _VITALS_INTERP_RE.search(rest)
        has_interp = interp_m is not None
        if has_interp:
            find_end = m.start("rest") + interp_m.end()
        else:
            find_end = obs_end

        entities.append({
            "id":          _normalise_id("d", idx),
            "sentence_id": sentence_id,
            "quote":       sentence_text[name_start:name_end],
            "labels":      ["PROCEDURE"],
            "assertion":   "present",
            "rationale":   "deterministic R8 vitals procedure",
            "source":      "deterministic",
        })
        idx += 1

        obs_text = sentence_text[name_start:obs_end].strip()
        if obs_text and obs_end > name_end:
            entities.append({
                "id":          _normalise_id("d", idx),
                "sentence_id": sentence_id,
                "quote":       obs_text,
                "labels":      ["OBSERVABLE_ENTITY"],
                "assertion":   "present",
                "rationale":   "deterministic R8 vitals observable",
                "source":      "deterministic",
            })
            idx += 1

        if has_interp:
            find_text = sentence_text[name_start:find_end].strip()
            if find_text:
                entities.append({
                    "id":          _normalise_id("d", idx),
                    "sentence_id": sentence_id,
                    "quote":       find_text,
                    "labels":      ["FINDING"],
                    "assertion":   "present",
                    "rationale":   "deterministic R8 vitals finding",
                    "source":      "deterministic",
                })
                idx += 1

    return entities


def extract_structured_entities(
    sentences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run deterministic extraction over all sentences.

    Args:
        sentences: list of {"sentence_id": int, "text": str, ...}

    Returns:
        Flat list of entity dicts, with "source": "deterministic".
    """
    entities: list[dict[str, Any]] = []
    idx = 1

    for sent in sentences:
        sid = sent.get("sentence_id", 0)
        text = sent.get("text") or ""
        if not text.strip():
            continue

        # Primary: try the strict Read-code-based lab detector
        pattern = detect_lab_pattern(text)
        if pattern.matched and pattern.test_name_span is not None:
            ts = pattern.test_name_span
            entities.append({
                "id":          _normalise_id("d", idx),
                "sentence_id": sid,
                "quote":       text[ts.start:ts.end].strip() or ts.text,
                "labels":      ["PROCEDURE"],
                "assertion":   "present",
                "rationale":   "deterministic R1 lab procedure",
                "source":      "deterministic",
            })
            idx += 1

            obs = pattern.observable_span
            if obs is not None:
                obs_text = text[obs.start:obs.end].strip() or obs.text
                entities.append({
                    "id":          _normalise_id("d", idx),
                    "sentence_id": sid,
                    "quote":       obs_text,
                    "labels":      ["OBSERVABLE_ENTITY"],
                    "assertion":   "present",
                    "rationale":   "deterministic R1 lab observable",
                    "source":      "deterministic",
                })
                idx += 1

            fnd = pattern.finding_span
            if fnd is not None:
                fnd_text = text[fnd.start:fnd.end].strip() or fnd.text
                entities.append({
                    "id":          _normalise_id("d", idx),
                    "sentence_id": sid,
                    "quote":       fnd_text,
                    "labels":      ["FINDING"],
                    "assertion":   "present",
                    "rationale":   "deterministic R1 lab finding",
                    "source":      "deterministic",
                })
                idx += 1

            continue  # lab_span_detector matched; skip vitals extraction

        # Fallback: try vitals pattern for non-coded lines
        vitals = _extract_vitals(text, sid, idx)
        if vitals:
            entities.extend(vitals)
            idx += len(vitals)

    return entities


def sentence_has_structured_content(text: str) -> bool:
    """Return True if a sentence looks like it has lab/vitals content."""
    if detect_lab_pattern(text).matched:
        return True
    return bool(_VITALS_PROCEDURE_RE.search(text))


def encounter_structured_sentences(
    sentences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return only the sentences that contain structured lab/vitals content."""
    return [
        s for s in sentences
        if sentence_has_structured_content(s.get("text") or "")
    ]
