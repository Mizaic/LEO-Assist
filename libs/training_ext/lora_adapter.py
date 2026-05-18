"""LoRA adapter wiring for the spaCy transformer backbone.

Atlas trace:
  DO: DO-A35D2D57
  DI: DI-37B3DC71

PEFT / LoRA is opt-in:

* When ``TRAINING_MODE=lora`` is set in the environment, the training job
  applies a LoRA wrapper to the Bio_ClinicalBERT backbone at the start of
  training. This exposes a small number of trainable parameters (rank
  ``LORA_RANK``, default 8) while keeping the transformer weights frozen,
  giving clinically-appropriate adaptation at a fraction of the full-tune
  memory cost.
* When ``TRAINING_MODE=full`` we train all parameters (current default if
  ``TRAINING_FROZEN_COMPONENTS`` does not include ``transformer``).
* When ``TRAINING_MODE=frozen`` (default) the transformer is frozen and only
  the downstream heads are trained — same behaviour as before Wave 4.

This module is side-effect-free on import. Registration with spaCy happens
via :func:`register_lora_callback` so importing the module from within a test
or CLI tool does not force a spaCy import.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Iterable

logger = logging.getLogger(__name__)


_DEFAULT_TARGET_MODULES: tuple[str, ...] = (
    "query",
    "key",
    "value",
    "dense",
)


@dataclass(frozen=True)
class LoRAConfig:
    """Subset of PEFT LoRA knobs exposed through env vars."""

    rank: int = 8
    alpha: int = 16
    dropout: float = 0.1
    target_modules: tuple[str, ...] = _DEFAULT_TARGET_MODULES
    bias: str = "none"

    @classmethod
    def from_env(cls) -> "LoRAConfig":
        def _int_env(name: str, default: int) -> int:
            raw = os.getenv(name, "").strip()
            if not raw:
                return default
            try:
                return int(raw)
            except ValueError:
                logger.warning(
                    "[lora] Ignoring invalid %s=%r; using %d", name, raw, default
                )
                return default

        def _float_env(name: str, default: float) -> float:
            raw = os.getenv(name, "").strip()
            if not raw:
                return default
            try:
                return float(raw)
            except ValueError:
                logger.warning(
                    "[lora] Ignoring invalid %s=%r; using %.2f", name, raw, default
                )
                return default

        raw_targets = os.getenv("LORA_TARGET_MODULES", "").strip()
        targets = tuple(
            m.strip() for m in raw_targets.split(",") if m.strip()
        ) or _DEFAULT_TARGET_MODULES
        return cls(
            rank=_int_env("LORA_RANK", 8),
            alpha=_int_env("LORA_ALPHA", 16),
            dropout=_float_env("LORA_DROPOUT", 0.1),
            target_modules=targets,
            bias=os.getenv("LORA_BIAS", "none").strip() or "none",
        )


def training_mode() -> str:
    """Return the requested training mode — ``"full"``, ``"frozen"``, or ``"lora"``."""
    raw = os.getenv("TRAINING_MODE", "frozen").strip().lower()
    if raw not in {"full", "frozen", "lora"}:
        logger.warning(
            "[lora] Ignoring unknown TRAINING_MODE=%r (expected full|frozen|lora); "
            "defaulting to 'frozen'",
            raw,
        )
        return "frozen"
    return raw


def apply_lora_to_hf_model(hf_model, config: LoRAConfig | None = None):
    """Wrap an HF transformer in a PEFT LoRA adapter in-place.

    Returns the PEFT-wrapped model. Safe no-op if PEFT is not installed; caller
    receives the original model back so training can continue (with a warning).
    """
    config = config or LoRAConfig.from_env()
    try:
        from peft import LoraConfig, TaskType, get_peft_model
    except ImportError:
        logger.warning(
            "[lora] peft is not installed — cannot apply LoRA; "
            "returning the original model. Install with `pip install peft`."
        )
        return hf_model

    lora_cfg = LoraConfig(
        r=config.rank,
        lora_alpha=config.alpha,
        lora_dropout=config.dropout,
        bias=config.bias,
        target_modules=list(config.target_modules),
        task_type=TaskType.FEATURE_EXTRACTION,
    )
    wrapped = get_peft_model(hf_model, lora_cfg)
    trainable, total = _count_params(wrapped)
    logger.info(
        "[lora] Applied LoRA (rank=%d alpha=%d targets=%s). Trainable params: "
        "%d / %d (%.4f%%)",
        config.rank,
        config.alpha,
        config.target_modules,
        trainable,
        total,
        (100 * trainable / total) if total else 0.0,
    )
    return wrapped


def _count_params(model) -> tuple[int, int]:
    try:
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total = sum(p.numel() for p in model.parameters())
        return trainable, total
    except Exception:
        return 0, 0


# ----------------------------------------------------------------------
# spaCy registry entry — only activates when the caller has imported spaCy.
# ----------------------------------------------------------------------


def register_lora_callback() -> None:
    """Register the ``leo_training.apply_lora.v1`` spaCy callback (idempotent).

    The callback receives the spaCy ``nlp`` object at the end of the
    ``[initialize]`` step and wraps the inner HuggingFace transformer with
    LoRA when ``TRAINING_MODE=lora``.
    """
    try:
        from spacy.util import registry
    except Exception as exc:
        logger.warning(
            "[lora] Could not import spaCy registry (%s); callback unavailable.",
            exc,
        )
        return

    if "leo_training.apply_lora.v1" in registry.callbacks:
        return

    @registry.callbacks("leo_training.apply_lora.v1")
    def _apply_lora_callback():
        def apply(nlp):
            if training_mode() != "lora":
                return nlp
            if "transformer" not in nlp.pipe_names:
                logger.warning(
                    "[lora] TRAINING_MODE=lora but no 'transformer' component "
                    "in pipeline — skipping."
                )
                return nlp
            transformer = nlp.get_pipe("transformer")
            hf_model = getattr(getattr(transformer, "model", None), "tokenizer", None)
            # spacy-transformers stores the torch backbone differently per
            # version — we try the common locations.
            hf_module = _extract_hf_module(transformer)
            if hf_module is None:
                logger.warning(
                    "[lora] Could not locate the inner HF torch model on the "
                    "spaCy transformer pipe; LoRA not applied."
                )
                return nlp
            wrapped = apply_lora_to_hf_model(hf_module, LoRAConfig.from_env())
            _install_hf_module(transformer, wrapped)
            return nlp

        return apply


def _extract_hf_module(transformer):
    for attr in ("transformer", "model", "_model"):
        obj = getattr(transformer, attr, None)
        if obj is None:
            continue
        for inner in ("transformer", "hf_model", "model"):
            candidate = getattr(obj, inner, None)
            if candidate is not None and hasattr(candidate, "named_parameters"):
                return candidate
        if hasattr(obj, "named_parameters"):
            return obj
    return None


def _install_hf_module(transformer, wrapped) -> None:
    for attr in ("transformer", "model"):
        obj = getattr(transformer, attr, None)
        if obj is None:
            continue
        for inner in ("transformer", "hf_model", "model"):
            if hasattr(obj, inner):
                setattr(obj, inner, wrapped)
                return
    logger.warning(
        "[lora] LoRA-wrapped model could not be re-installed on the "
        "spaCy transformer pipe."
    )


def target_modules_for_family(family: str) -> Iterable[str]:
    """Sensible default target modules per-architecture for quick experimentation."""
    family = family.lower()
    if "bert" in family or "clinical" in family:
        return _DEFAULT_TARGET_MODULES
    if "roberta" in family:
        return _DEFAULT_TARGET_MODULES
    if "gpt" in family or "llama" in family:
        return ("q_proj", "v_proj")
    return _DEFAULT_TARGET_MODULES
