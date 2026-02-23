"""
TF-IDF character 3-gram + HNSW approximate nearest neighbour candidate generator.

Adapted from scispaCy's ``candidate_generation.py``. Builds a sparse TF-IDF
index over all KB alias strings and uses nmslib HNSW for sub-millisecond
cosine-similarity lookups.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import NamedTuple

import joblib
import nmslib
import numpy as np
import scipy.sparse
from sklearn.feature_extraction.text import TfidfVectorizer

from .knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


class MentionCandidate(NamedTuple):
    concept_id: str
    aliases: list[str]
    similarities: list[float]


class CandidateGenerator:
    """Batch candidate retrieval via TF-IDF + approximate nearest neighbours."""

    def __init__(
        self,
        kb: KnowledgeBase,
        ann_index: nmslib.FloatIndex,
        tfidf_vectorizer: TfidfVectorizer,
        ann_concept_aliases: list[str],
    ) -> None:
        self.kb = kb
        self._ann_index = ann_index
        self._vectorizer = tfidf_vectorizer
        self._aliases = ann_concept_aliases

    def __call__(
        self,
        mention_texts: list[str],
        k: int = 30,
    ) -> list[list[MentionCandidate]]:
        if not mention_texts:
            return []

        vectors = self._vectorizer.transform(mention_texts)
        neighbours = self._ann_index.knnQueryBatch(vectors, k=k, num_threads=4)

        batch_results: list[list[MentionCandidate]] = []
        for indices, distances in neighbours:
            concept_candidates: dict[str, MentionCandidate] = {}
            for idx, dist in zip(indices, distances):
                alias = self._aliases[idx]
                similarity = 1.0 - dist
                concept_ids = self.kb.alias_to_cuis.get(alias.lower(), set())
                for cid in concept_ids:
                    if cid in concept_candidates:
                        old = concept_candidates[cid]
                        concept_candidates[cid] = MentionCandidate(
                            cid,
                            old.aliases + [alias],
                            old.similarities + [similarity],
                        )
                    else:
                        concept_candidates[cid] = MentionCandidate(
                            cid, [alias], [similarity]
                        )
            batch_results.append(list(concept_candidates.values()))

        return batch_results

    @classmethod
    def from_artifacts(cls, kb: KnowledgeBase, data_dir: str | Path) -> CandidateGenerator:
        data_dir = Path(data_dir)
        logger.info("Loading TF-IDF + ANN artifacts from %s", data_dir)

        vectorizer = joblib.load(data_dir / "tfidf_vectorizer.joblib")
        ann_index = nmslib.init(method="hnsw", space="cosinesimil_sparse")
        ann_index.loadIndex(
            str(data_dir / "nmslib_index.bin"),
            load_data=True,
        )
        ann_index.setQueryTimeParams({"efSearch": 200})
        with open(data_dir / "concept_aliases.json") as f:
            aliases = json.load(f)

        logger.info("Loaded index with %d alias vectors", len(aliases))
        return cls(kb, ann_index, vectorizer, aliases)


def create_tfidf_ann_index(
    kb: KnowledgeBase,
    output_dir: str | Path,
) -> CandidateGenerator:
    """Build a TF-IDF + ANN index from a KnowledgeBase and save artifacts."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_aliases: list[str] = []
    for entity in kb.cui_to_entity.values():
        all_aliases.append(entity.canonical_name)
        all_aliases.extend(entity.aliases)

    all_aliases = list(dict.fromkeys(all_aliases))
    logger.info("Fitting TF-IDF on %d unique aliases", len(all_aliases))

    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 3),
        min_df=10,
        dtype=np.float32,
    )
    tfidf_matrix = vectorizer.fit_transform(all_aliases)

    # Remove aliases with all-zero vectors
    row_norms = scipy.sparse.linalg.norm(tfidf_matrix, axis=1)
    non_zero_mask = row_norms > 0
    kept_aliases = [a for a, keep in zip(all_aliases, non_zero_mask) if keep]
    kept_matrix = tfidf_matrix[non_zero_mask]
    logger.info(
        "Kept %d / %d aliases after removing zero vectors",
        len(kept_aliases),
        len(all_aliases),
    )

    logger.info("Building nmslib HNSW index")
    ann_index = nmslib.init(method="hnsw", space="cosinesimil_sparse")
    ann_index.addDataPointBatch(kept_matrix)
    ann_index.createIndex({"M": 100, "efConstruction": 2000}, print_progress=True)
    ann_index.setQueryTimeParams({"efSearch": 200})

    # Save artifacts
    ann_index.saveIndex(str(output_dir / "nmslib_index.bin"), save_data=True)
    joblib.dump(vectorizer, output_dir / "tfidf_vectorizer.joblib")
    with open(output_dir / "concept_aliases.json", "w") as f:
        json.dump(kept_aliases, f)

    logger.info("Artifacts saved to %s", output_dir)
    return CandidateGenerator(kb, ann_index, vectorizer, kept_aliases)
