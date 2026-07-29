"""Shared deterministic matcher for NG12 source_row_text backfill.

Ports the exact matching strategy the wizard already uses client-side
(services/ui/.../SentenceEditor/recommendationTextMatch.ts and
.../HighlightWizard/leafTextMatch.ts) so every backfill script (dry-run
spike, Stage 1 apply, Stage 2 LLM-assisted verify) shares one definition
of "does this candidate phrase anchor onto the guideline text".

Unlike the TS version (which only needs a highlight span), every span
function here returns the REAL substring of the guideline text -- never
the candidate string itself -- so a written source_row_text is always
verbatim guideline wording, even when the candidate was proposed by an
LLM with slightly different casing/spelling.
"""

from __future__ import annotations

import re
from typing import Any, NamedTuple

LEAF_KINDS = {"CONCEPT", "DEMOGRAPHIC", "OBSERVATION"}
STOPWORDS = {
    "a", "an", "the", "of", "with", "and", "or", "in", "to", "for",
    "is", "are", "any", "following", "these", "that",
}
MIN_TOKEN_OVERLAP_SCORE = 0.5
_DASH_RE = re.compile("[\u2010-\u2015\u2212]")
_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")
_TAG_SUFFIX_RE = re.compile(r"\s*\(([a-z][a-z /-]*?)\)\s*$", re.IGNORECASE)


class MatchSpan(NamedTuple):
    start: int
    end: int
    matched_text: str
    score: float


def friendly_term(raw: str | None) -> str:
    if not raw:
        return ""
    trimmed = raw.strip()
    stripped = _TAG_SUFFIX_RE.sub("", trimmed).strip()
    return stripped or trimmed


def normalise_for_compare(s: str) -> str:
    collapsed = _DASH_RE.sub("-", s.strip().lower())
    return re.sub(r"\s+", " ", collapsed)


def js_number_str(value: Any) -> str:
    """Mirror JS `String(Number(value))`: whole floats drop the ".0"."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f == int(f):
        return str(int(f))
    return str(f)


def tokenize(text: str) -> list[tuple[str, int, int]]:
    return [
        (m.group(0).lower(), m.start(), m.end()) for m in _TOKEN_RE.finditer(text)
    ]


def exact_match_span(text: str, candidate: str) -> MatchSpan | None:
    needle = normalise_for_compare(candidate)
    if not needle:
        return None
    collapsed: list[str] = []
    offsets: list[int] = []
    last_was_space = True
    for i, raw in enumerate(text):
        ch = "-" if _DASH_RE.match(raw) else raw
        is_space = ch.isspace()
        if is_space:
            if last_was_space:
                continue
            collapsed.append(" ")
            offsets.append(i)
            last_was_space = True
        else:
            collapsed.append(ch.lower())
            offsets.append(i)
            last_was_space = False
    haystack = "".join(collapsed)
    idx = haystack.find(needle)
    if idx < 0:
        return None
    start = offsets[idx]
    last_idx = idx + len(needle) - 1
    end = offsets[last_idx] + 1
    return MatchSpan(start, end, text[start:end], 1.0)


def token_overlap_span(text: str, candidate: str) -> MatchSpan | None:
    candidate_tokens = [t for t, _, _ in tokenize(candidate) if t not in STOPWORDS]
    if not candidate_tokens:
        return None
    candidate_set = set(candidate_tokens)
    text_tokens = tokenize(text)
    if not text_tokens:
        return None

    window_size = max(1, len(candidate_tokens))
    best: tuple[float, int, int] | None = None
    for size in range(max(1, window_size - 1), window_size + 3):
        for i in range(0, len(text_tokens) - size + 1):
            window = [(t, s, e) for t, s, e in text_tokens[i : i + size] if t not in STOPWORDS]
            if not window:
                continue
            window_words = {t for t, _, _ in window}
            hits = len(window_words & candidate_set)
            coverage = hits / len(candidate_set)
            precision = hits / len(window_words)
            score = (coverage + precision) / 2
            if best is None or score > best[0]:
                best = (score, i, i + size - 1)

    if best is None or best[0] < MIN_TOKEN_OVERLAP_SCORE:
        return None
    score, start_idx, end_idx = best
    start = text_tokens[start_idx][1]
    end = text_tokens[end_idx][2]
    return MatchSpan(start, end, text[start:end], score)


def best_match_span(text: str | None, candidate: str | None) -> MatchSpan | None:
    """Best real-text span anchoring `candidate`, or None if it doesn't
    appear (exactly, or via token overlap >= MIN_TOKEN_OVERLAP_SCORE)."""
    if not text or not candidate:
        return None
    exact = exact_match_span(text, candidate)
    if exact:
        return exact
    return token_overlap_span(text, candidate)


def first_matching_span(text: str | None, candidates: list[str]) -> MatchSpan | None:
    """Try `candidates` in priority order; return the first real-text span
    that anchors. Order matters: put the most trustworthy provenance
    (e.g. a captured raw_term/source_text) first."""
    for candidate in candidates:
        span = best_match_span(text, candidate)
        if span:
            return span
    return None


_AGE_LABEL_RULES = [
    (lambda op, n, n2: op in ("<=", "<") and n <= 18, "children"),
    (lambda op, n, n2: op in ("<=", "<") and n <= 18, "children and young people"),
    (lambda op, n, n2: op in ("<=", "<") and n in (24, 25), "children and young people"),
    (lambda op, n, n2: op in ("<=", "<") and n in (15, 16), "children"),
    (lambda op, n, n2: op == "between" and n == 16 and n2 == 24, "young people"),
    (lambda op, n, n2: op in (">=", ">") and n in (18, 25), "adults"),
]


def demographic_candidates(node: dict[str, Any]) -> list[str]:
    out: list[str] = []
    raw_term = node.get("raw_term")
    if raw_term and isinstance(raw_term, str) and raw_term.strip():
        out.append(raw_term.strip())

    value = node.get("value")
    if value is None or value == "":
        return out
    field_name = node.get("field")
    op = node.get("operator") or ">="

    # "between" sometimes stores value as [low, high] instead of value/value2.
    value2 = node.get("value2")
    if op == "between" and isinstance(value, list) and len(value) == 2:
        value, value2 = value[0], value[1]
    value_s = js_number_str(value)

    if field_name == "sex":
        sex = value_s.lower()
        if sex in ("m", "male"):
            return out + ["male", "men", "man"]
        if sex in ("f", "female"):
            return out + ["female", "women", "woman"]
        return out + [value_s]
    if field_name != "age":
        return out

    try:
        n = float(value_s)
    except ValueError:
        n = float("nan")
    n2 = float(value2) if value2 not in (None, "") else float("nan")
    value2_s = js_number_str(value2) if value2 not in (None, "") else ""

    for predicate, label in _AGE_LABEL_RULES:
        if predicate(op, n, n2) and label not in out:
            out.append(label)

    if op == "between" and value2 not in (None, ""):
        out.append(f"{value_s} to {value2_s}")
        out.append(f"aged {value_s} to {value2_s}")
    elif op == "<":
        out.append(f"aged under {value_s}")
        out.append(f"under the age of {value_s}")
        out.append(f"aged {value_s} or less")
    elif op == "<=":
        out.append(f"aged {value_s} or under")
        out.append(f"aged {value_s} and under")
        out.append(f"aged under {value_s}")
    else:
        suffix = {">=": "or over", ">": "or more", "=": ""}.get(op, "")
        out.append(f"aged {value_s} {suffix}".strip())
        if op == ">=":
            out.append(f"aged {value_s} and over")
    return out


def concept_candidates(
    node: dict[str, Any], extra_synonyms: dict[str, list[str]] | None = None
) -> list[str]:
    criterion = node.get("criterion") or {}
    candidates: list[str] = []
    source_text = criterion.get("source_text")
    if source_text and isinstance(source_text, str) and source_text.strip():
        candidates.append(source_text.strip())

    raws = [criterion.get("term"), criterion.get("preferred_term")]
    raws += [seed.get("preferred_term") for seed in criterion.get("seeds") or []]
    for raw in raws:
        if not raw or not raw.strip():
            continue
        friendly = friendly_term(raw)
        if friendly:
            candidates.append(friendly)
        if raw.strip() != friendly:
            candidates.append(raw.strip())
    if extra_synonyms:
        for raw in raws:
            if not raw:
                continue
            key = friendly_term(raw).lower()
            candidates.extend(extra_synonyms.get(key, []))
    return candidates


def observation_candidate(node: dict[str, Any]) -> str | None:
    obs = node.get("observation") or {}
    return obs.get("observable_term")


def walk_leaves(node: dict[str, Any]) -> list[dict[str, Any]]:
    kind = (node.get("kind") or "").upper()
    if kind in LEAF_KINDS:
        return [node]
    out: list[dict[str, Any]] = []
    for child in node.get("children") or []:
        out.extend(walk_leaves(child))
    return out


def leaf_candidates(
    leaf: dict[str, Any], extra_synonyms: dict[str, list[str]] | None = None
) -> tuple[str, list[str]]:
    """Returns (default_label, candidate_phrases) for one leaf, by kind."""
    kind = (leaf.get("kind") or "").upper()
    if kind == "CONCEPT":
        candidates = concept_candidates(leaf, extra_synonyms)
        return (candidates[0] if candidates else "(no preferred_term)", candidates)
    if kind == "DEMOGRAPHIC":
        candidates = demographic_candidates(leaf)
        return (candidates[0] if candidates else "(unfilled)", candidates)
    term = observation_candidate(leaf)
    candidates = [term] if term else []
    return (term or "(no observable_term)", candidates)
