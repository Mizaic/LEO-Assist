from libs.staging.tnm_parser import parse_tnm_triplet


def test_parses_basic_tnm_triplet() -> None:
    parsed = parse_tnm_triplet("T2N1M0")
    assert parsed is not None
    assert parsed.t == "T2"
    assert parsed.n == "N1"
    assert parsed.m == "M0"
    assert parsed.prefix == ""


def test_parses_prefixed_tnm_triplet() -> None:
    parsed = parse_tnm_triplet("pT3bN0M0")
    assert parsed is not None
    assert parsed.t == "T3B"
    assert parsed.n == "N0"
    assert parsed.m == "M0"
    assert parsed.prefix == "P"


def test_returns_none_for_non_tnm() -> None:
    assert parse_tnm_triplet("Stage IIIA") is None
