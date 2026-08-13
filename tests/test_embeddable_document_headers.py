"""Embeddable patient document file security header exceptions."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "services" / "api" / "app" / "main.py"


def test_embeddable_document_file_paths_use_sameorigin_headers():
    src = MAIN.read_text(encoding="utf-8")
    assert "_is_embeddable_patient_document_file" in src
    assert 'response.headers["X-Frame-Options"] = "SAMEORIGIN"' in src
    assert 'response.headers["Content-Security-Policy"] = "frame-ancestors \'self\'"' in src
    assert "/documents/" in src
    assert 'endswith("/file")' in src
