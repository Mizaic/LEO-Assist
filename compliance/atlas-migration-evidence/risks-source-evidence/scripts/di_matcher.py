"""TF-IDF-style Atlas DI relevance matcher.

Given the text of a risk (failure_mode + cause + effect + hazard description),
score every Atlas DI title and return the top-N most likely mitigating DIs.

Common words like "review", "coding", "patient" get downweighted by IDF so
results don't all collapse to the same handful of generic DIs.

Public API:
    build_index(atlas_dis) -> Index
    match(risk_text, index, top_n=5, min_score=0.20) -> list[Match]
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

STOPWORDS = frozenset({
    "the", "a", "an", "is", "of", "to", "and", "or", "in", "on", "for", "by",
    "with", "be", "at", "as", "from", "into", "this", "that", "are", "has",
    "have", "not", "but", "it", "their", "they", "when", "which", "all",
    "any", "each", "so", "such", "after", "before", "while", "via", "per",
    "without", "between", "within", "across",
})


@dataclass(frozen=True)
class AtlasDI:
    dc_id: str
    title: str


@dataclass
class Index:
    dis: list[AtlasDI]
    di_tokens: list[set[str]]
    idf: dict[str, float]


@dataclass
class Match:
    dc_id: str
    title: str
    score: float
    overlap: list[str]


def tokens(text: str) -> set[str]:
    text = re.sub(r"[^a-zA-Z0-9 ]", " ", (text or "").lower())
    return {w for w in text.split() if len(w) > 2 and w not in STOPWORDS}


def build_index(atlas_dis: list[dict]) -> Index:
    """Build a token + IDF index over Atlas DI titles."""
    dis = [AtlasDI(dc_id=d["dcId"], title=d["title"]) for d in atlas_dis]
    di_tokens = [tokens(d.title) for d in dis]
    df: dict[str, int] = {}
    for tset in di_tokens:
        for t in tset:
            df[t] = df.get(t, 0) + 1
    n = max(1, len(dis))
    idf = {t: math.log((n + 1) / (c + 0.5)) + 1.0 for t, c in df.items()}
    return Index(dis=dis, di_tokens=di_tokens, idf=idf)


def _weighted_score(risk_tokens: set[str], di_tokens: set[str],
                    idf: dict[str, float]) -> tuple[float, list[str]]:
    overlap = sorted(risk_tokens & di_tokens)
    if not overlap:
        return 0.0, []
    overlap_weight = sum(idf.get(t, 1.0) for t in overlap)
    di_weight = sum(idf.get(t, 1.0) for t in di_tokens) or 1.0
    coverage = overlap_weight / di_weight
    distinctiveness = overlap_weight / max(len(overlap), 1)
    return coverage * math.sqrt(distinctiveness), overlap


def match(risk_text: str, index: Index,
          top_n: int = 5, min_score: float = 0.20) -> list[Match]:
    risk_tokens = tokens(risk_text)
    if not risk_tokens:
        return []
    scored: list[Match] = []
    for di, di_tokset in zip(index.dis, index.di_tokens):
        score, overlap = _weighted_score(risk_tokens, di_tokset, index.idf)
        if score >= min_score:
            scored.append(Match(dc_id=di.dc_id, title=di.title,
                                score=round(score, 3), overlap=overlap))
    scored.sort(key=lambda m: m.score, reverse=True)
    return scored[:top_n]
