"""Domain-adaptive MLM pretraining for Bio_ClinicalBERT.

Atlas trace:
  DO: DO-A35D2D57
  DI: DI-37B3DC71

Motivation
----------
Bio_ClinicalBERT was pretrained on MIMIC-III (US ICU notes). Our target
corpus is UK primary care / oncology text, which has a noticeably different
register (e.g. "consultant", "pathway", "MDT", anonymised patient IDs). A
short MLM continuation run over our own de-identified text produces a
domain-adapted checkpoint that the spaCy trainer can then point at via
``TRAINING_HF_BASE_MODEL=<checkpoint-dir>``.

Usage::

    python -m scripts.mlm_pretrain \
        --corpus-file data/clinical_corpus.txt \
        --output-dir models/bioclinical_domain_v1 \
        --epochs 3 --batch-size 16

The corpus file must contain one line per sentence (or short passage).
De-identify the corpus *before* running this script.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("mlm_pretrain")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--corpus-file",
        required=True,
        type=Path,
        help="Plain-text file, one passage per line. Must be de-identified.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Destination directory for the domain-adapted HF checkpoint.",
    )
    parser.add_argument(
        "--base-model",
        default=os.getenv("TRAINING_HF_BASE_MODEL", "emilyalsentzer/Bio_ClinicalBERT"),
        help="Starting HuggingFace checkpoint.",
    )
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--max-seq-length", type=int, default=256)
    parser.add_argument(
        "--mlm-probability",
        type=float,
        default=0.15,
        help="Probability of masking each token (HuggingFace default: 0.15).",
    )
    parser.add_argument(
        "--gradient-accumulation-steps",
        type=int,
        default=4,
    )
    parser.add_argument(
        "--fp16",
        action="store_true",
        help="Enable mixed precision (CUDA only).",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> None:
    try:
        from datasets import Dataset
        from transformers import (
            AutoModelForMaskedLM,
            AutoTokenizer,
            DataCollatorForLanguageModeling,
            Trainer,
            TrainingArguments,
        )
    except ImportError as exc:
        logger.error(
            "This script requires the `transformers` + `datasets` packages. "
            "Install with `pip install transformers datasets`."
        )
        raise SystemExit(2) from exc

    corpus_path: Path = args.corpus_file
    if not corpus_path.exists():
        logger.error("Corpus file not found: %s", corpus_path)
        raise SystemExit(2)

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading tokenizer + base model: %s", args.base_model)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = AutoModelForMaskedLM.from_pretrained(args.base_model)

    lines = [
        line.strip()
        for line in corpus_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    logger.info("Loaded %d non-empty passages from corpus", len(lines))
    if not lines:
        raise SystemExit("Corpus is empty — nothing to pretrain on.")

    dataset = Dataset.from_dict({"text": lines})

    def tokenize(batch):
        return tokenizer(
            batch["text"],
            truncation=True,
            padding="max_length",
            max_length=args.max_seq_length,
        )

    tokenised = dataset.map(tokenize, batched=True, remove_columns=["text"])
    collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=True,
        mlm_probability=args.mlm_probability,
    )
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        fp16=args.fp16,
        save_total_limit=2,
        save_strategy="epoch",
        logging_steps=50,
        report_to=[],
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenised,
        data_collator=collator,
    )
    logger.info("Starting MLM pretraining — %d epochs", args.epochs)
    trainer.train()
    logger.info("Saving domain-adapted checkpoint to %s", output_dir)
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    logger.info(
        "Done. Point TRAINING_HF_BASE_MODEL=%s to use it in the next spaCy run.",
        output_dir,
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    run(_parse_args(argv if argv is not None else sys.argv[1:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
