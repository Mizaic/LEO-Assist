"""Train a spaCy NER + EntityLinker model from exported gold data.

Reads entities.jsonl (spaCy NER training format) and kb.jsonl (knowledge base
entries) produced by the MedSpaCy export endpoint, then trains a tok2vec + NER
pipeline and builds a spaCy KnowledgeBase for entity linking.

Usage:
    python scripts/train_medspacy.py \
        --entities exports/medspacy_*_entities.jsonl \
        --kb exports/medspacy_*_kb.jsonl \
        --output models/medspacy_clinical_ner \
        --epochs 30
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from pathlib import Path

import spacy
from spacy.tokens import DocBin
from spacy.training import Example
from spacy.kb import InMemoryLookupKB
from thinc.api import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_DIR = ROOT / "models" / "medspacy_clinical_ner"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--entities", type=Path, required=True, help="Path to entities.jsonl"
    )
    parser.add_argument("--kb", type=Path, required=True, help="Path to kb.jsonl")
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_MODEL_DIR, help="Model output directory"
    )
    parser.add_argument(
        "--base-model", default="en_core_web_sm", help="Base spaCy model to build on"
    )
    parser.add_argument("--epochs", type=int, default=30, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=8, help="Training batch size")
    parser.add_argument(
        "--eval-split", type=float, default=0.2, help="Fraction held out for eval"
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--dropout", type=float, default=0.35, help="Dropout rate")
    return parser.parse_args()


def load_entities(path: Path) -> list[tuple[str, dict]]:
    """Load [text, {"entities": [[start, end, label], ...]}] JSONL lines."""
    data = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                text, annotations = row[0], row[1]
                data.append((text, annotations))
            except (json.JSONDecodeError, IndexError, KeyError) as exc:
                logger.warning("Skipping line %d: %s", line_no, exc)
    logger.info("Loaded %d entity training examples from %s", len(data), path)
    return data


def load_kb_entries(path: Path) -> list[dict[str, str]]:
    """Load kb.jsonl rows: {evidence, concept_id, term}."""
    entries = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    logger.info("Loaded %d KB entries from %s", len(entries), path)
    return entries


def collect_labels(data: list[tuple[str, dict]]) -> set[str]:
    """Collect unique NER labels from training data."""
    labels = set()
    for _, ann in data:
        for ent in ann.get("entities", []):
            labels.add(ent[2])
    return labels


def build_knowledge_base(
    nlp: spacy.Language,
    kb_entries: list[dict[str, str]],
) -> InMemoryLookupKB:
    """Build a spaCy InMemoryLookupKB from kb.jsonl entries."""
    kb = InMemoryLookupKB(
        vocab=nlp.vocab, entity_vector_length=nlp.vocab.vectors_length or 64
    )

    concept_map: dict[str, list[str]] = {}
    for entry in kb_entries:
        cid = entry.get("concept_id", "").strip()
        mention = entry.get("evidence", "").strip()
        if cid and mention:
            concept_map.setdefault(cid, []).append(mention)

    for cid in concept_map:
        kb.add_entity(
            entity=cid,
            freq=len(concept_map[cid]),
            entity_vector=[0.0] * (nlp.vocab.vectors_length or 64),
        )

    for cid, mentions in concept_map.items():
        for mention in mentions:
            kb.add_alias(alias=mention, entities=[cid], probabilities=[1.0])

    logger.info(
        "KB built: %d entities, %d aliases",
        kb.get_size_entities(),
        kb.get_size_aliases(),
    )
    return kb


def create_training_examples(
    nlp: spacy.Language,
    data: list[tuple[str, dict]],
) -> list[Example]:
    """Convert raw data to spaCy Example objects, filtering misaligned spans."""
    examples = []
    skipped = 0
    for text, ann in data:
        doc = nlp.make_doc(text)
        entities = ann.get("entities", [])
        try:
            example = Example.from_dict(doc, {"entities": entities})
            if example.reference.ents:
                examples.append(example)
            else:
                skipped += 1
        except Exception:
            skipped += 1
    if skipped:
        logger.warning("Skipped %d examples due to alignment issues", skipped)
    logger.info("Created %d valid training examples", len(examples))
    return examples


def train_ner(
    nlp: spacy.Language,
    train_examples: list[Example],
    eval_examples: list[Example],
    epochs: int,
    batch_size: int,
    dropout: float,
) -> dict[str, float]:
    """Train the NER component and return evaluation metrics."""
    if "ner" not in nlp.pipe_names:
        ner = nlp.add_pipe("ner", last=True)
    else:
        ner = nlp.get_pipe("ner")

    for example in train_examples:
        for ent in example.reference.ents:
            ner.add_label(ent.label_)

    other_pipes = [p for p in nlp.pipe_names if p != "ner"]
    with nlp.disable_pipes(*other_pipes):
        optimizer = nlp.begin_training()
        best_f1 = 0.0
        best_epoch = 0

        for epoch in range(1, epochs + 1):
            random.shuffle(train_examples)
            losses = {}
            batches = [
                train_examples[i : i + batch_size]
                for i in range(0, len(train_examples), batch_size)
            ]
            for batch in batches:
                nlp.update(batch, sgd=optimizer, drop=dropout, losses=losses)

            ner_loss = losses.get("ner", 0.0)

            scores = nlp.evaluate(eval_examples)
            f1 = scores.get("ents_f", 0.0)
            precision = scores.get("ents_p", 0.0)
            recall = scores.get("ents_r", 0.0)

            if f1 > best_f1:
                best_f1 = f1
                best_epoch = epoch

            if epoch % 5 == 0 or epoch == 1 or epoch == epochs:
                logger.info(
                    "Epoch %d/%d - loss=%.4f, P=%.2f%%, R=%.2f%%, F1=%.2f%%",
                    epoch,
                    epochs,
                    ner_loss,
                    precision * 100,
                    recall * 100,
                    f1 * 100,
                )

    final_scores = nlp.evaluate(eval_examples)
    return {
        "precision": final_scores.get("ents_p", 0.0),
        "recall": final_scores.get("ents_r", 0.0),
        "f1": final_scores.get("ents_f", 0.0),
        "best_f1": best_f1,
        "best_epoch": best_epoch,
    }


def main() -> int:
    args = parse_args()
    random.seed(args.seed)

    if not args.entities.exists():
        logger.error("Entities file not found: %s", args.entities)
        return 1
    if not args.kb.exists():
        logger.error("KB file not found: %s", args.kb)
        return 1

    logger.info("Loading base model: %s", args.base_model)
    try:
        nlp = spacy.load(args.base_model)
    except OSError:
        logger.error(
            "Base model '%s' not found. Install with: python -m spacy download %s",
            args.base_model,
            args.base_model,
        )
        return 1

    data = load_entities(args.entities)
    if not data:
        logger.error("No training data found in %s", args.entities)
        return 1

    kb_entries = load_kb_entries(args.kb)

    all_examples = create_training_examples(nlp, data)
    if len(all_examples) < 5:
        logger.error("Too few valid examples (%d). Need at least 5.", len(all_examples))
        return 1

    random.shuffle(all_examples)
    split_idx = max(1, int(len(all_examples) * (1 - args.eval_split)))
    train_examples = all_examples[:split_idx]
    eval_examples = all_examples[split_idx:]
    logger.info(
        "Train: %d examples, Eval: %d examples", len(train_examples), len(eval_examples)
    )

    labels = collect_labels(data)
    logger.info("NER labels: %s", sorted(labels))

    logger.info(
        "Training NER for %d epochs (batch=%d, dropout=%.2f)",
        args.epochs,
        args.batch_size,
        args.dropout,
    )
    metrics = train_ner(
        nlp,
        train_examples,
        eval_examples,
        epochs=args.epochs,
        batch_size=args.batch_size,
        dropout=args.dropout,
    )

    logger.info(
        "Final metrics - P=%.2f%%, R=%.2f%%, F1=%.2f%% (best F1=%.2f%% at epoch %d)",
        metrics["precision"] * 100,
        metrics["recall"] * 100,
        metrics["f1"] * 100,
        metrics["best_f1"] * 100,
        metrics["best_epoch"],
    )

    if kb_entries:
        logger.info("Building knowledge base...")
        kb = build_knowledge_base(nlp, kb_entries)
        kb_path = args.output / "kb"
        kb_path.mkdir(parents=True, exist_ok=True)
        kb.to_disk(str(kb_path))
        logger.info("KB saved to %s", kb_path)

    args.output.mkdir(parents=True, exist_ok=True)
    nlp.to_disk(str(args.output))
    logger.info("Model saved to %s", args.output)

    metrics_path = args.output / "training_metrics.json"
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "precision": metrics["precision"],
                "recall": metrics["recall"],
                "f1": metrics["f1"],
                "best_f1": metrics["best_f1"],
                "best_epoch": metrics["best_epoch"],
                "epochs": args.epochs,
                "train_examples": len(train_examples),
                "eval_examples": len(eval_examples),
                "labels": sorted(labels),
                "kb_entities": len(kb_entries) if kb_entries else 0,
            },
            f,
            indent=2,
        )
    logger.info("Training metrics saved to %s", metrics_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
