"""Central registry of Wave 0-5 training/inference feature flags.

Atlas trace:
  DO: DO-236545C8, DO-A35D2D57, DO-54397CCD
  DI: DI-37B3DC71, DI-3FDBB57B

Each flag has:
  * ``name`` — the env var that turns it on / off.
  * ``default`` — the on/off default when the env var is unset.
  * ``wave`` — the plan wave that introduced it (0..5).
  * ``description`` — single-line explanation.

The purpose of this module is twofold:

1. Provide one readable inventory rather than scattering flags across the
   trainer/evaluator/job_runner/inference code.
2. Let tests and the UI enumerate the active flag state for the runbook and
   Atlas audit evidence exports.

Call :func:`snapshot` at any time for the current flag state:

    from libs.training_ext.feature_flags import snapshot
    flags = snapshot()
    print(flags["TRAINING_MODE"].active)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class FeatureFlag:
    name: str
    default: str
    wave: int
    description: str


FLAGS: tuple[FeatureFlag, ...] = (
    # Wave 1 — config hygiene knobs.
    FeatureFlag(
        "TRAINING_WINDOW_TOKENS",
        "0",
        1,
        "Override strided transformer window size (0 = config default).",
    ),
    FeatureFlag(
        "TRAINING_STRIDE_TOKENS",
        "0",
        1,
        "Override strided transformer stride size (0 = config default).",
    ),
    FeatureFlag(
        "TRAINING_LR_SCHEDULE",
        "warmup_linear",
        1,
        "Learning-rate schedule: warmup_linear (default) or cosine "
        "(cosine requires thinc>=9.0 / spaCy 4.x; auto-detected at runtime).",
    ),
    # Wave 3 — calibration + multi-seed + K-fold.
    FeatureFlag(
        "CALIBRATION_FIT_ISOTONIC",
        "true",
        3,
        "Fit per-label isotonic regression during calibration (default on; "
        "gracefully falls back when support is below CALIBRATION_MIN_SUPPORT).",
    ),
    FeatureFlag(
        "CALIBRATION_MIN_SUPPORT",
        "10",
        3,
        "Per-label positive support threshold for threshold sweep.",
    ),
    FeatureFlag(
        "TRAINING_SEEDS",
        "",
        3,
        "Comma-separated seeds for multi-seed training (empty = single run).",
    ),
    FeatureFlag(
        "TRAINING_SKIP_CALIBRATION",
        "false",
        3,
        "Skip Wave 3 calibration phase (useful for fast-path smoke runs).",
    ),
    # Wave 4 — LoRA / pseudo-labelling / domain-adaptive pretrain.
    FeatureFlag(
        "TRAINING_MODE",
        "frozen",
        4,
        "Training mode: full | frozen | lora.",
    ),
    FeatureFlag(
        "LORA_RANK",
        "8",
        4,
        "LoRA rank when TRAINING_MODE=lora.",
    ),
    FeatureFlag(
        "PSEUDO_LABEL_MIN_CONFIDENCE",
        "0.85",
        4,
        "Minimum confidence for pseudo-label emission.",
    ),
    # Wave 5 — inference threshold unification + observability + Neo4j gates.
    FeatureFlag(
        "PRECISION_GATES_FROM_NEO4J",
        "true",
        5,
        "Read (:PrecisionGate) nodes for per-label F1 gates; fallback to defaults.",
    ),
    FeatureFlag(
        "DRIFT_SINK_ENABLED",
        "true",
        5,
        "Emit per-inference drift records to DRIFT_SINK_DIR (JSONL).",
    ),
    FeatureFlag(
        "DRIFT_SINK_DIR",
        "/var/lib/leo/drift",
        5,
        "Directory for daily drift JSONL files (mount a persistent volume).",
    ),
    FeatureFlag(
        "REVIEW_QUEUE_DIR",
        "/var/lib/leo/review_queue",
        5,
        "Directory for the active learning review queue (persistent volume).",
    ),
    FeatureFlag(
        "MLFLOW_TRACKING_URI",
        "",
        5,
        "MLflow tracking URI (empty = logger is a no-op).",
    ),
)


@dataclass(frozen=True)
class FlagState:
    flag: FeatureFlag
    value: str
    active: bool


def snapshot(flags: Iterable[FeatureFlag] = FLAGS) -> dict[str, FlagState]:
    """Return a {flag_name: FlagState} view for the current process env."""
    out: dict[str, FlagState] = {}
    for flag in flags:
        raw = os.getenv(flag.name, flag.default)
        active = raw.strip().lower() not in {"", "false", "0", "no", "off"}
        out[flag.name] = FlagState(flag=flag, value=raw, active=active)
    return out


def to_markdown() -> str:
    """Render the flag inventory as a Markdown table for the runbook."""
    header = "| Wave | Flag | Default | Description |\n|------|------|---------|-------------|"
    rows: list[str] = []
    for flag in sorted(FLAGS, key=lambda f: (f.wave, f.name)):
        rows.append(
            f"| {flag.wave} | `{flag.name}` | `{flag.default or '(empty)'}` | {flag.description} |"
        )
    return "\n".join([header, *rows])
