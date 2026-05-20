"""Tests for multi-label inference endpoint.

Covers VT-LEO-AI-107-TC-002:
- Old model (no 'sc' key) falls back to doc.ents without exception.
- New model with doc.spans['sc'] returns one EntityOut per span-label pair.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


def _make_span(text: str, label: str, start: int, end: int, score: str = ""):
    """Build a minimal spaCy-like span mock."""
    span = MagicMock()
    span.text = text
    span.label_ = label
    span.start_char = start
    span.end_char = end
    span.kb_id_ = score
    return span


def _make_doc(spans_sc=None, ents=None):
    """Return a mock spaCy Doc."""
    doc = MagicMock()
    doc.spans = {}
    if spans_sc is not None:
        doc.spans["sc"] = spans_sc
    doc.ents = ents or []
    return doc


def _make_nlp(doc):
    nlp = MagicMock()
    nlp.return_value = doc
    return nlp


class _FakeSentence:
    def __init__(self, sentence_id="s0", text="text", start=0, end=4):
        self.sentence_id = sentence_id
        self.text = text
        self.start = start
        self.end = end


class TestInferenceMultiLabel(unittest.TestCase):
    """VT-107-TC-002: multi-label inference returns multiple EntityOut."""

    def _run_extract(self, nlp, sentences):
        """Run the extract logic directly without spinning up FastAPI."""
        from app.main import _loader

        with patch.object(_loader, "nlp", new=nlp):
            from fastapi.testclient import TestClient
            from app.main import app

            client = TestClient(app)
            payload = {
                "text": " ".join(s.text for s in sentences),
                "sentences": [
                    {
                        "sentence_id": s.sentence_id,
                        "text": s.text,
                        "start": s.start,
                        "end": s.end,
                    }
                    for s in sentences
                ],
            }
            response = client.post("/extract", json=payload)
        return response

    def test_sc_absent_falls_back_to_ents_no_exception(self):
        ent = _make_span("diabetes", "DISORDER", 0, 8)
        doc = _make_doc(spans_sc=None, ents=[ent])
        nlp = _make_nlp(doc)

        with patch("app.main._loader") as mock_loader:
            mock_loader.nlp = nlp
            mock_loader.active_version = "v0.9"
            mock_loader.model_name = "test"
            mock_loader.calibration = None
            with patch("libs.deid.deidentify") as mock_deid:
                mock_deid.return_value = MagicMock(text="diabetes")
                from fastapi.testclient import TestClient
                from app.main import app
                from libs.auth.service_auth import verify_service_token

                app.dependency_overrides[verify_service_token] = lambda: None
                client = TestClient(app)
                resp = client.post(
                    "/extract",
                    json={
                        "text": "diabetes",
                        "sentences": [
                            {
                                "sentence_id": "s0",
                                "text": "diabetes",
                                "start": 0,
                                "end": 8,
                            }
                        ],
                    },
                )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["entity_count"], 1)
        self.assertEqual(data["entities"][0]["label"], "DISORDER")

    def test_sc_present_returns_multi_label_entities(self):
        text = "Furosemide increased to 40mg BD"
        span1 = _make_span(text, "MEDICINAL_PRODUCT", 0, len(text))
        span2 = _make_span(text, "PROCEDURE", 0, len(text))
        doc = _make_doc(spans_sc=[span1, span2])
        nlp = _make_nlp(doc)

        with patch("app.main._loader") as mock_loader:
            mock_loader.nlp = nlp
            mock_loader.active_version = "v1.0"
            mock_loader.model_name = "test"
            mock_loader.calibration = None
            with patch("libs.deid.deidentify") as mock_deid:
                mock_deid.return_value = MagicMock(text=text)
                from fastapi.testclient import TestClient
                from app.main import app
                from libs.auth.service_auth import verify_service_token

                app.dependency_overrides[verify_service_token] = lambda: None
                client = TestClient(app)
                resp = client.post(
                    "/extract",
                    json={
                        "text": text,
                        "sentences": [
                            {
                                "sentence_id": "s0",
                                "text": text,
                                "start": 0,
                                "end": len(text),
                            }
                        ],
                    },
                )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["entity_count"], 2)
        labels = {e["label"] for e in data["entities"]}
        self.assertIn("MEDICINAL_PRODUCT", labels)
        self.assertIn("PROCEDURE", labels)

    def test_calibration_threshold_filters_low_scoring_spans(self):
        from libs.training_ext.inference_calibration import InferenceCalibration

        text = "chest xray requested"
        high = _make_span("chest xray", "PROCEDURE", 0, 10, score="0.20")
        low = _make_span("requested", "FINDING", 11, len(text), score="0.05")
        doc = _make_doc(spans_sc=[high, low])
        nlp = _make_nlp(doc)
        calibration = InferenceCalibration(
            default_threshold=0.5,
            per_label={
                "PROCEDURE": {"threshold": 0.10},
                "FINDING": {"threshold": 0.10},
            },
            is_verified=True,
        )

        with patch("app.main._loader") as mock_loader:
            mock_loader.nlp = nlp
            mock_loader.active_version = "v1.0"
            mock_loader.model_name = "test"
            mock_loader.calibration = calibration
            with patch("libs.deid.deidentify") as mock_deid:
                mock_deid.return_value = MagicMock(text=text)
                from fastapi.testclient import TestClient
                from app.main import app
                from libs.auth.service_auth import verify_service_token

                app.dependency_overrides[verify_service_token] = lambda: None
                client = TestClient(app)
                resp = client.post(
                    "/extract",
                    json={
                        "text": text,
                        "sentences": [
                            {
                                "sentence_id": "s0",
                                "text": text,
                                "start": 0,
                                "end": len(text),
                            }
                        ],
                    },
                )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["entity_count"], 1)
        entity = data["entities"][0]
        self.assertEqual(entity["label"], "PROCEDURE")
        self.assertEqual(entity["source_meta"]["threshold"], 0.1)
