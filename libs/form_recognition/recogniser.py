"""Recognise which taught form each referral document is.

Each document gets exactly one of four outcomes:

- Recognised: one taught form explains it well, clearly ahead of the rest;
- Unrecognised: it looks like a form, but no taught form explains it;
- NotAForm: it reads like a letter or email, and no taught form is close;
- RecognitionFailed: scoring raised, so nobody knows (fail closed).

Only Recognised may skip a person's review. Unrecognised and
RecognitionFailed always pause the run (``bundle_needs_review``). There is
no fallback by hash, by organisation and service, or by whole bundle.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48. Risk R-B88CCFD6.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Iterable, Union

from libs.form_recognition.anchors import compile_schemas
from libs.form_recognition.bundle import split_chunks
from libs.form_recognition.likeness import Likeness, assess_likeness
from libs.form_recognition.scoring import DocumentView, Score, score_schema
from libs.form_recognition.settings import (
    MARGIN_MIN,
    MAX_UNEXPLAINED,
    OPTION_COVERAGE_MIN,
    ORDER_MIN,
    PARTIAL_RECALL,
    PRECISION_MIN,
    RECALL_MIN,
)
from libs.pipeline.form_schema_normalizer import FormSchema

logger = logging.getLogger(__name__)


def _score_dict(score: Score | None) -> dict[str, object] | None:
    return None if score is None else score.to_dict()


@dataclass(frozen=True)
class _Outcome:
    title: str = ""
    chunk_indexes: tuple[int, ...] = ()

    kind = "outcome"

    def summary(self) -> str:
        return f"{self.kind}: {self.to_dict()}"

    def to_dict(self) -> dict[str, object]:
        return {
            "outcome": self.kind,
            "title": self.title,
            "chunk_indexes": list(self.chunk_indexes),
        }


@dataclass(frozen=True)
class _Scored(_Outcome):
    best: Score | None = None
    runner_up: Score | None = None
    likeness: Likeness | None = None

    def to_dict(self) -> dict[str, object]:
        data = super().to_dict()
        data["best"] = _score_dict(self.best)
        data["runner_up"] = _score_dict(self.runner_up)
        data["likeness"] = None if self.likeness is None else self.likeness.to_dict()
        return data


@dataclass(frozen=True)
class Recognised(_Scored):
    schema: FormSchema | None = None
    kind = "recognised"

    def to_dict(self) -> dict[str, object]:
        data = super().to_dict()
        data["fingerprint"] = self.schema.fingerprint if self.schema else ""
        return data


@dataclass(frozen=True)
class Unrecognised(_Scored):
    reason: str = "form_not_recognised"
    kind = "unrecognised"

    def to_dict(self) -> dict[str, object]:
        data = super().to_dict()
        data["reason"] = self.reason
        return data


@dataclass(frozen=True)
class NotAForm(_Scored):
    kind = "not_a_form"


@dataclass(frozen=True)
class RecognitionFailed(_Outcome):
    error: str = ""
    kind = "recognition_failed"

    def to_dict(self) -> dict[str, object]:
        data = super().to_dict()
        data["error"] = self.error
        return data


Outcome = Union[Recognised, Unrecognised, NotAForm, RecognitionFailed]


def _rank(score: Score) -> tuple[float, float]:
    return (score.recall, score.precision)


def explains_layout(best: Score) -> bool:
    """True when the form explains enough of the letter's headings and boxes."""
    if len(best.unexplained) <= MAX_UNEXPLAINED:
        return True
    return best.precision >= PRECISION_MIN


def _passes(best: Score, runner_up: Score | None) -> bool:
    if best.recall < RECALL_MIN or best.option_coverage < OPTION_COVERAGE_MIN:
        return False
    if best.order < ORDER_MIN or not explains_layout(best):
        return False
    return runner_up is None or best.recall - runner_up.recall >= MARGIN_MIN


def _decide(scores: list[Score], likeness: Likeness, by_fp: dict) -> Outcome:
    ranked = sorted(scores, key=_rank, reverse=True)
    best = ranked[0] if ranked else None
    runner_up = ranked[1] if len(ranked) > 1 else None
    common = {"best": best, "runner_up": runner_up, "likeness": likeness}
    if best is not None and _passes(best, runner_up):
        return Recognised(schema=by_fp[best.fingerprint], **common)
    if likeness.form_like or (best is not None and best.recall >= PARTIAL_RECALL):
        return Unrecognised(**common)
    return NotAForm(**common)


def recognise_document(text: str, schemas: Iterable[FormSchema]) -> Outcome:
    """Return the outcome for one document. Never raises."""
    try:
        compiled = compile_schemas(schemas)
        view = DocumentView(text)
        scores = [score_schema(view, item) for item in compiled]
        by_fp = {item.fingerprint: item.schema for item in compiled}
        return _decide(scores, assess_likeness(text), by_fp)
    except Exception as exc:  # fail closed: the run degrades and pauses
        logger.exception("form recognition failed")
        return RecognitionFailed(error=f"{type(exc).__name__}: {exc}")


def recognise_bundle(chunks: list[str], schemas: Iterable[FormSchema]) -> list[Outcome]:
    """Return one outcome per document in a bundle of stored chunks."""
    schema_list = list(schemas)
    results: list[Outcome] = []
    for doc in split_chunks(chunks):
        outcome = recognise_document(doc.text, schema_list)
        results.append(
            replace(outcome, title=doc.title, chunk_indexes=doc.chunk_indexes)
        )
    return results


def bundle_needs_review(results: Iterable[Outcome]) -> bool:
    """True when any document is unrecognised or could not be scored."""
    return any(isinstance(r, (Unrecognised, RecognitionFailed)) for r in results)
