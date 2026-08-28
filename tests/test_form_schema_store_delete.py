"""Tests for delete_form_schema parameter-passing bug fix.

VT: delete_form_schema must call client.run with fingerprint as a keyword
argument, not as a positional dict.
"""

from libs.pipeline.form_schema_store import delete_form_schema


class _StubClient:
    """Records how run() was called."""

    def __init__(self, return_rows):
        self.calls = []
        self._return_rows = return_rows

    def run(self, query, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        return self._return_rows


def test_delete_form_schema_passes_fingerprint_as_kwarg():
    """client.run must receive fingerprint as a keyword argument."""
    stub = _StubClient(return_rows=[{"schema_id": "abc-123"}])
    delete_form_schema(stub, "fp-test-001")

    assert len(stub.calls) == 1, "run() should be called exactly once"
    call = stub.calls[0]
    assert call["args"] == (), "no positional args beyond query expected"
    assert (
        call["kwargs"].get("fingerprint") == "fp-test-001"
    ), "fingerprint must be passed as a keyword argument"


def test_delete_form_schema_returns_true_when_row_has_schema_id():
    """Returns True when the stub yields a row containing schema_id."""
    stub = _StubClient(return_rows=[{"schema_id": "abc-123"}])
    assert delete_form_schema(stub, "fp-test-001") is True


def test_delete_form_schema_returns_false_when_no_rows():
    """Returns False when the stub yields no rows."""
    stub = _StubClient(return_rows=[])
    assert delete_form_schema(stub, "fp-test-001") is False
