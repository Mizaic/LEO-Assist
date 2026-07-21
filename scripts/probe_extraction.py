"""Ad-hoc extraction probe -- not part of the test suite.

Usage:
    python -m scripts.probe_extraction

Runs the LLM extractor + full post-processing stack against a small set of
sentences and prints the resulting entity list.
"""
from __future__ import annotations

import json
import logging
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env")
load_dotenv(ROOT / ".env", override=False)

try:
    from libs.keyvault.loader import load_keyvault_secrets

    load_keyvault_secrets()
except Exception:
    pass

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

SENTENCES = [
    "Moderate left pleural effusion with irregular left pleural thickening and mild left hemithoracic volume loss",
    "Unilateral right pleural effusion with nodular pleural thickening along the lateral chest wall.",
    "Diffuse left pleural thickening with blunting of the left costophrenic angle and reduced left lung volume",
    "Right-sided pleural-based opacity with associated pleural effusion and diaphragmatic pleural thickening.",
    "Large left pleural effusion with lobulated pleural abnormality and ipsilateral volume loss.",
]

ENCOUNTER_TEXT = "\n".join(SENTENCES)


def _make_chunks(sentences: list[str]) -> list:
    from libs.nlp.sentence_splitter import SentenceChunk

    chunks = []
    offset = 0
    for i, text in enumerate(sentences):
        chunks.append(
            SentenceChunk(
                sentence_id=f"s{i}",
                text=text,
                start=offset,
                end=offset + len(text),
            )
        )
        offset += len(text) + 1
    return chunks


def _items_to_dicts(items: list) -> list[dict]:
    from libs.pipeline_graph.subgraphs.extraction import _items_to_dicts

    return _items_to_dicts(items)


def main() -> None:
    from libs.pipeline_graph.subgraphs._extractor import build_extractor
    from libs.pipeline.post_processing import run_post_processing
    from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1

    extractor = build_extractor(system_prompt=EXTRACTION_SYSTEM_V1)
    chunks = _make_chunks(SENTENCES)

    print("Running LLM extraction ...")
    items = extractor.extract_batch(ENCOUNTER_TEXT, chunks)

    print(f"  Raw entities from LLM: {len(items)}")
    entity_dicts = _items_to_dicts(items)

    print("Running post-processing ...")
    processed = run_post_processing(ENCOUNTER_TEXT, entity_dicts)

    print(f"  Entities after post-processing: {len(processed)}\n")

    _DISPLAY_KEYS = ("text", "label", "assertion", "normalized", "value", "unit")
    for ent in processed:
        row = {k: v for k, v in ent.items() if k in _DISPLAY_KEYS and v}
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
