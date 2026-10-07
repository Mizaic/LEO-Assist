"""Cut stored chunks at document boundaries.

A stored chunk can hold the end of one document and the start of the
next. Each recognised form must be applied only to its own document, so
every chunk is cut into pieces that each belong to one document.

Atlas trace: DI-E21DF9EF (AC6: a form applies only to its own document)
-> DO-E458EEC5 -> VT-B13F7C48.
"""

from __future__ import annotations

from libs.form_recognition.bundle import chunk_pieces, split_chunks

_FORM = "--- Document: form.doc ---\nSection A: Symptoms\n[x] Bleeding"
_ERS = "--- Document: Clinical Information.pdf ---\nClinical Information"


def test_pieces_rebuild_every_chunk_exactly() -> None:
    chunks = [_FORM + "\n\nMore form text\n" + _ERS, "Reason for referral"]
    pieces = chunk_pieces(chunks)
    assert ["".join(text for _doc, text in row) for row in pieces] == chunks


def test_a_chunk_spanning_two_documents_is_cut_at_the_marker() -> None:
    chunks = [_FORM + "\n" + _ERS]
    (row,) = chunk_pieces(chunks)
    assert [doc for doc, _text in row] == [0, 1]
    assert row[1][1].startswith("--- Document: Clinical Information.pdf")


def test_piece_document_index_matches_split_chunks() -> None:
    chunks = [_FORM, "tail of the form", _ERS]
    docs = split_chunks(chunks)
    pieces = chunk_pieces(chunks)
    assert docs[0].title == "form.doc"
    assert [row[0][0] for row in pieces] == [0, 0, 1]


def test_text_outside_any_document_has_no_owner() -> None:
    chunks = ["  ", _FORM]
    pieces = chunk_pieces(chunks)
    assert pieces[0] == [(None, "  ")]
    assert pieces[1][0][0] == 0


def test_a_bundle_without_markers_is_one_document() -> None:
    pieces = chunk_pieces(["Dear Doctor", "Yours sincerely"])
    assert pieces == [[(0, "Dear Doctor")], [(0, "Yours sincerely")]]
