"""Unit tests for libs.pipeline.extraction_response_parse."""

from __future__ import annotations

from libs.pipeline.extraction_response_parse import parse_extraction_terms_response


def test_empty_input():
    data, src = parse_extraction_terms_response("")
    assert data == {}
    assert src == "empty_input"


def test_valid_json():
    data, src = parse_extraction_terms_response('{"terms": []}')
    assert data == {"terms": []}
    assert src == "json_ok"


def test_adds_terms_key():
    data, src = parse_extraction_terms_response("{}")
    assert data == {"terms": []}
    assert src == "json_ok"


def test_preamble_and_brace_trim():
    raw = 'Intro text {"terms": [{"text": "x"}]} trailing'
    data, src = parse_extraction_terms_response(raw)
    assert src == "json_ok"
    assert len(data["terms"]) == 1


def test_fenced_json_anywhere():
    raw = """# Extraction Result

```json
{"terms": [{"text": "cough"}]}
```
"""
    data, src = parse_extraction_terms_response(raw)
    assert src == "json_ok"
    assert len(data["terms"]) == 1


def test_prose_no_entities():
    raw = """# Extraction Result

**No codable clinical entities identified.**

## Rationale

All sentences are administrative.
"""
    data, src = parse_extraction_terms_response(raw)
    assert src == "prose_empty"
    assert data == {"terms": []}


def test_invalid_not_prose():
    data, src = parse_extraction_terms_response("not json at all")
    assert data == {}
    assert src == "failed"
