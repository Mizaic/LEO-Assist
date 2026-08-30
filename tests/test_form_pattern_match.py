"""Taught form patterns must match the printed token.

Atlas:
  DI: DI-5C9CA57B
  DI: DI-26546721
"""

from libs.pipeline.form_pattern_match import safe_search


def test_unclosed_bracket_is_a_literal_printed_token() -> None:
    line = "Patient Fitness (ECOG STATUS) : 0 [ ] 1 [X] 3 [ ] 4 [ ]"
    match = safe_search("1 [", line)
    assert match is not None
    assert match.group(0) == "1 ["
    assert "F12" not in line[match.start() : match.end() + 2]
