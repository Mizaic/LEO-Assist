"""
Aggregate a 0-1 confidence score for each coded entity.

Combines: TF-IDF cosine similarity, context certainty (negated/uncertain
reduce downstream utility but don't reduce coding confidence), source
reliability (exact > fulltext > abbreviation expansion > Neo4j fallback),
and whether the entity came via abbreviation expansion.
"""


from spacy.language import Language
from spacy.tokens import Doc, Span

_SOURCE_WEIGHTS: dict[str | None, float] = {
    "local_kb": 1.0,
    "read_code": 1.0,
    "neo4j_fallback": 0.7,
    None: 0.5,
}


@Language.factory("confidence_scorer")
class ConfidenceScorer:
    """Aggregate linker + source reliability into a 0-1 confidence score."""

    def __init__(self, nlp: Language, name: str = "confidence_scorer"):
        self.nlp = nlp
        self.name = name

    def __call__(self, doc: Doc) -> Doc:
        for ent in doc.ents:
            score = _compute_confidence(ent)
            ent._.confidence = score
        return doc


def _compute_confidence(ent: Span) -> float:
    linker_score = ent._.linker_score if ent._.linker_score else 0.0
    source_weight = _SOURCE_WEIGHTS.get(ent._.source, 0.5)

    is_abbrev = ent._.is_abbreviation
    abbrev_penalty = 0.9 if is_abbrev else 1.0

    confidence = linker_score * source_weight * abbrev_penalty
    return round(min(max(confidence, 0.0), 1.0), 4)
