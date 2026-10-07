"""Every form-recognition threshold, in one place.

Tuned on the labelled set in ``tests/fixtures/form_recognition`` so that
no document is matched to the wrong form. Change a value only with the
corpus test green: ``tests/test_form_recognition_corpus.py``.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
"""

from __future__ import annotations

# Anchor matching.
FUZZY_CUTOFF = 88.0
SHORT_ALT_MAX_WORDS = 2
SHORT_ALT_MAX_CHARS = 12

# Anchor weights before inverse document frequency.
SECTION_WEIGHT = 2.0
ITEM_WEIGHT = 1.0

# A Recognised decision needs every one of these. Recall is low on purpose:
# a national form with a page lost in conversion must still be recognised.
# Option coverage and unexplained headings do the discriminating.
RECALL_MIN = 0.45
OPTION_COVERAGE_MIN = 0.65
ORDER_MIN = 0.70
MARGIN_MIN = 0.15

# Unexplained headings and options: a few are tolerated (a file title, a
# local note); more than this many, at under this precision, is a new form.
MAX_UNEXPLAINED = 2
PRECISION_MIN = 0.85

# Any taught form this well covered makes the document form-like.
PARTIAL_RECALL = 0.35
