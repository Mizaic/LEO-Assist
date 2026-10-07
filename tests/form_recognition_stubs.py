"""Test stubs for the chunk loader's recognition seam.

Patch ``libs.pipeline.document_chunk_loader._recognise_chunks`` with one of
these when a test needs a known recognition outcome without a graph or a
recogniser threshold in the way.
"""

from __future__ import annotations

from typing import Callable

from libs.form_recognition.bundle import split_chunks
from libs.form_recognition.recogniser import Outcome, Recognised, Unrecognised
from libs.pipeline.form_schema_normalizer import FormSchema

RecogniseFn = Callable[..., list[Outcome]]


def recognise_all_as(schema: FormSchema) -> RecogniseFn:
    """Every document in the bundle is recognised as ``schema``."""

    def _fake(raw_texts: list[str], *_args: object, **_kwargs: object):
        return [
            Recognised(title=doc.title, chunk_indexes=doc.chunk_indexes, schema=schema)
            for doc in split_chunks(raw_texts)
        ]

    return _fake


def recognise_none() -> RecogniseFn:
    """Every document in the bundle is an unrecognised form."""

    def _fake(raw_texts: list[str], *_args: object, **_kwargs: object):
        return [
            Unrecognised(title=doc.title, chunk_indexes=doc.chunk_indexes)
            for doc in split_chunks(raw_texts)
        ]

    return _fake
