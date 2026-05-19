"""spaCy training subprocess wrapper.

Atlas trace:
  DO: DO-A35D2D57
  DI: DI-37B3DC71
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A35D2D57")

Runs ``python -m app.run_spacy_train_cli train`` (registers ``leo_training.TransformerListener``)
in a subprocess, streams stdout/stderr line
by line to the job log, and returns the path to the best model output.

If TRAINING_BASE_MODEL_VERSION is set, the promoted blob model is downloaded
first and used as the NER component's initial weights (warm start).
The Bio_ClinicalBERT transformer backbone is always loaded from HuggingFace
Hub (cached in HF_HOME) — it is never packed into the blob artifact.

``TRAINING_JOB_TIMEOUT_S`` caps **wall-clock** time for a single ``spacy train``
subprocess. The previous implementation only passed ``timeout=`` to ``wait()``
after log streaming finished, so it did not end long runs. A watchdog thread
enforces the limit. Unset or ``0`` disables the cap. ``TRAINING_SEEDS`` runs
one subprocess per seed; the cap applies to **each** run.
"""

from __future__ import annotations

import glob as _glob
import logging
import os
import re
import subprocess
import sys
import sysconfig
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from libs.utils.device_resolver import AcceleratorDecision, resolve_accelerator

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "config" / "base.cfg"
_TRAINING_APP_ROOT = Path(__file__).resolve().parents[1]
_HF_MODEL = os.getenv("TRAINING_HF_BASE_MODEL", "emilyalsentzer/Bio_ClinicalBERT")
_FROZEN = os.getenv("TRAINING_FROZEN_COMPONENTS", "transformer")
_BASE_MODEL_VERSION = os.getenv("TRAINING_BASE_MODEL_VERSION", "").strip()

_VALID_LR_SCHEDULES = {"warmup_linear", "cosine"}

_PRE_E313_DYNAMICS: dict[str, str] = {
    "window": "128",
    "stride": "96",
    "hidden_size": "128",
    "dropout": "0.1",
    "accumulate_gradient": "1",
    "patience": "1600",
    "max_steps": "20000",
    "eval_frequency": "200",
    "start": "64",
    "stop": "256",
    "use_averages": "false",
    "warmup_steps": "250",
    "total_steps": "20000",
    "initial_rate": "0.00005",
}


def _parse_training_wall_timeout_s() -> int:
    """Return wall-clock cap in seconds for one ``spacy train`` subprocess.

    Reads ``TRAINING_JOB_TIMEOUT_S`` at call time. Unset, ``0``, or empty
    disables the cap. Deploy environments may set a finite value.
    """
    raw = os.environ.get("TRAINING_JOB_TIMEOUT_S")
    if raw is None:
        return 0
    raw = raw.strip()
    if not raw or raw == "0":
        return 0
    try:
        return max(0, int(raw, 10))
    except ValueError:
        logger.warning(
            "Invalid TRAINING_JOB_TIMEOUT_S=%r; using no wall cap",
            os.environ.get("TRAINING_JOB_TIMEOUT_S"),
        )
        return 0


def _parse_seeds() -> list[int]:
    """Return the list of seeds to iterate over for multi-seed training.

    Controlled by ``TRAINING_SEEDS`` (comma-separated ints). Empty / unset
    means a single run at the config's default seed.
    """
    raw = os.getenv("TRAINING_SEEDS", "").strip()
    if not raw:
        return []
    seeds: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            seeds.append(int(token))
        except ValueError:
            logger.warning(
                "[trainer] Ignoring non-integer seed %r in TRAINING_SEEDS", token
            )
    return seeds


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "[trainer] Ignoring invalid %s=%r (expected int); using %d",
            name,
            raw,
            default,
        )
        return default


def _is_cosine_available() -> bool:
    """Return True only when warmup_cosine.v1 is registered in the training venv.

    thinc >= 8.4 ships warmup_cosine.v1; older versions do not.  We probe
    at runtime so a cosine request on an old thinc degrades gracefully
    instead of failing inside the spaCy subprocess with a RegistryError.
    """
    try:
        from thinc.api import registry as _thinc_registry  # type: ignore[import]
        return "warmup_cosine.v1" in _thinc_registry.schedules.get_all()
    except Exception:
        return False


def _resolve_lr_schedule() -> str:
    raw = os.getenv("TRAINING_LR_SCHEDULE", "warmup_linear").strip().lower()
    if raw not in _VALID_LR_SCHEDULES:
        logger.warning(
            "[trainer] Ignoring invalid TRAINING_LR_SCHEDULE=%r "
            "(expected one of %s); defaulting to warmup_linear",
            raw,
            sorted(_VALID_LR_SCHEDULES),
        )
        return "warmup_linear"
    if raw == "cosine" and not _is_cosine_available():
        logger.warning(
            "[trainer] TRAINING_LR_SCHEDULE=cosine requested but "
            "warmup_cosine.v1 is not registered in the training environment "
            "(thinc >= 8.4 required). Falling back to warmup_linear."
        )
        return "warmup_linear"
    return raw


def _resolve_ablation_profile() -> str:
    raw = os.getenv("TRAINING_ABLATION_PROFILE", "").strip().lower()
    if raw in {"", "current"}:
        return "current"
    if raw == "pre_e313_dynamics":
        return raw
    logger.warning(
        "[trainer] Ignoring invalid TRAINING_ABLATION_PROFILE=%r", raw
    )
    return "current"


def _replace_config_scalar(config_text: str, key: str, value: str) -> str:
    return re.sub(
        rf"(?m)^{re.escape(key)}\s*=\s*.+$",
        f"{key} = {value}",
        config_text,
        count=1,
    )


def _apply_ablation_profile(config_text: str) -> str:
    profile = _resolve_ablation_profile()
    if profile != "pre_e313_dynamics":
        return config_text
    for key, value in _PRE_E313_DYNAMICS.items():
        config_text = _replace_config_scalar(config_text, key, value)
    return config_text


def _register_nvidia_dll_dirs() -> None:
    """Register nvidia pip-wheel DLL directories with the Windows DLL loader.

    CuPy 14's `[ctk]` extra installs CUDA DLLs into per-package subdirectories
    (e.g. site-packages/nvidia/cublas/bin/).  On Windows, Python extension
    modules (.pyd files) cannot find DLLs via PATH — they require the directory
    to be registered via os.add_dll_directory().  Call this once before any
    cupy sub-module import.
    """
    site_packages = sysconfig.get_path("purelib")
    for dll in _glob.glob(
        os.path.join(site_packages, "nvidia", "**", "*.dll"),
        recursive=True,
    ):
        dll_dir = os.path.dirname(dll)
        try:
            os.add_dll_directory(dll_dir)
        except (OSError, AttributeError):
            pass  # add_dll_directory only exists on Windows Python 3.8+


def _probe_cupy_cuda() -> tuple[bool, str]:
    """Return whether CuPy/CUDA is truly usable for spaCy training."""
    try:
        # Register nvidia wheel DLL dirs so Windows can find cublas, nvrtc, etc.
        _register_nvidia_dll_dirs()
        import cupy
        import cupy.cublas  # thinc/spaCy require this on GPU startup

        # Touch runtime APIs to fail fast if CUDA DLLs are genuinely missing.
        cupy.cuda.runtime.getDeviceCount()
        cupy.array([1.0])
        return True, ""
    except Exception as exc:
        return False, f"cupy cuda preflight failed: {type(exc).__name__}: {exc}"


def _requested_training_accelerator() -> str:
    """Resolve requested accelerator from env, preserving old TRAINING_USE_GPU."""
    explicit = os.getenv("TRAINING_ACCELERATOR", "").strip().lower()
    if explicit in {"auto", "cpu", "cuda", "mps"}:
        return explicit
    if os.getenv("TRAINING_USE_GPU", "true").lower() in ("false", "0", "no"):
        return "cpu"
    return "auto"


def _resolve_training_accelerator() -> AcceleratorDecision:
    """Resolve and validate accelerator for training workloads."""
    decision = resolve_accelerator(
        _requested_training_accelerator(),
        prefer_mps_on_macos=True,
        min_macos_major_for_mps=int(os.getenv("MPS_MIN_MACOS_MAJOR", "26")),
        enforce_apple_silicon_for_mps=True,
    )
    if decision.resolved != "cuda":
        return decision
    ok, reason = _probe_cupy_cuda()
    if ok:
        return decision
    logger.warning(
        "CuPy/CUDA training preflight failed — falling back to CPU: %s", reason
    )
    return AcceleratorDecision(
        requested=decision.requested,
        resolved="cpu",
        fallback_applied=True,
        fallback_reason=reason,
        platform_name=decision.platform_name,
        machine=decision.machine,
        macos_major=decision.macos_major,
    )


def _build_env() -> dict:
    """Return a clean subprocess env for spaCy training.

    CuPy 14 (ctk variant) calls os.add_dll_directory() internally when it
    imports, registering the nvidia pip-wheel bin/ dirs with the Windows DLL
    loader.  We must NOT prepend those dirs to PATH: PyTorch ships its own
    CUDA 12.4 cublas64_12.dll in torch/lib/ and loads it at import time.
    Prepending the pip-wheel dir (CUDA 12.9 cuBLAS) would cause it to be
    found first, creating a version conflict and CUBLAS_STATUS_NOT_INITIALIZED.

    Rely on CuPy 14's own _setup_win32_dll_directory() for CUDA DLL discovery.
    """
    env = dict(os.environ)

    # --- Strip bad CUDA_PATH ------------------------------------------------
    # If CUDA_PATH points somewhere without a bin/ subdir CuPy's
    # os.add_dll_directory() raises FileNotFoundError.
    cuda_path = env.get("CUDA_PATH", "").strip()
    if cuda_path and not os.path.isdir(os.path.join(cuda_path, "bin")):
        env.pop("CUDA_PATH", None)

    env["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("HF_HOME", os.getenv("HF_HOME", "/tmp/hf_cache"))
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    training_root = str(_TRAINING_APP_ROOT)
    env["PYTHONPATH"] = (
        f"{training_root}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else training_root
    )
    return env


def _fetch_warm_start_model(version: str, log: Callable[[str], None]) -> Optional[Path]:
    """Download a promoted model blob and return the local model directory.

    Only the NER head weights are used — the transformer is always cold-started
    from Bio_ClinicalBERT. Returns None (and logs a warning) on any failure so
    training continues without warm-start rather than blocking the job.
    """
    try:
        from libs.model_store import ModelStore

        store = ModelStore()
        log(f"[warm-start] Downloading base model version {version}…")
        model_dir = store.download(version)
        log(f"[warm-start] Base model ready at {model_dir}")
        return model_dir
    except Exception as exc:
        log(f"[warm-start] WARNING: failed to download version {version}: {exc}")
        log("[warm-start] Continuing without warm-start (cold init).")
        return None


def run_training_with_seeds(
    work_dir: Path,
    *,
    train_path: Path,
    dev_path: Path,
    log_fn: Optional[Callable[[str], None]] = None,
) -> tuple[Path, dict]:
    """Run training across seeds (if ``TRAINING_SEEDS`` is set) and pick best.

    Falls back to :func:`run_training` when only a single seed is configured.
    Reads ``model-best/meta.json`` after each run and keeps the model with the
    highest ``performance.spans_sc_f`` (spancat F1) or ``performance.ents_f``
    as a legacy fallback.
    """
    import json as _json

    seeds = _parse_seeds()

    def _log(msg: str) -> None:
        logger.info("[trainer] %s", msg)
        if log_fn:
            log_fn(msg)

    if len(seeds) <= 1:
        single_seed = seeds[0] if seeds else None
        return run_training(
            work_dir,
            train_path=train_path,
            dev_path=dev_path,
            log_fn=log_fn,
            seed=single_seed,
        )

    _log(f"Multi-seed training with {len(seeds)} seeds: {seeds}")
    best: tuple[Path, dict, float, int] | None = None
    all_runs: list[dict] = []
    for seed in seeds:
        seed_dir = work_dir / f"seed_{seed}"
        seed_dir.mkdir(parents=True, exist_ok=True)
        _log(f"Seed {seed}: training into {seed_dir}")
        model_path, accel_meta = run_training(
            seed_dir,
            train_path=train_path,
            dev_path=dev_path,
            log_fn=log_fn,
            seed=seed,
        )
        meta_file = model_path / "meta.json"
        f1 = 0.0
        if meta_file.exists():
            try:
                performance = _json.loads(meta_file.read_text()).get("performance", {})
                f1 = float(
                    performance.get("spans_sc_f")
                    or performance.get("ents_f")
                    or 0.0
                )
            except Exception as exc:
                _log(f"Seed {seed}: could not parse meta.json ({exc}) — treating F1=0")
        _log(f"Seed {seed}: dev F1={f1:.4f}")
        all_runs.append({"seed": seed, "f1": round(f1, 4), "model_path": str(model_path)})
        if best is None or f1 > best[2]:
            best = (model_path, accel_meta, f1, seed)

    assert best is not None
    model_path, accel_meta, f1, winning_seed = best
    _log(f"Multi-seed winner: seed={winning_seed} F1={f1:.4f}")
    accel_meta = dict(accel_meta)
    accel_meta["multi_seed_runs"] = all_runs
    accel_meta["multi_seed_winner"] = winning_seed
    return model_path, accel_meta


def run_training(
    work_dir: Path,
    *,
    train_path: Path,
    dev_path: Path,
    log_fn: Optional[Callable[[str], None]] = None,
    seed: Optional[int] = None,
) -> tuple[Path, dict]:
    """Run spaCy training and return the path to the best model.

    Retry strategy (each attempt gets its own named config file):
      1. Primary run — GPU if available, frozen components as configured.
      2. Unfreeze transformer — if listener ``nO`` init error (before MPS fail-fast).
      3. CPU retry — if GPU attempt fails (skipped when MPS fail-fast is on).

    Args:
        work_dir: Temporary working directory; output written to work_dir/output/.
        train_path: Path to train.spacy DocBin.
        dev_path: Path to dev.spacy DocBin.
        log_fn: Optional callable for streaming log lines.

    Returns:
        Path to the trained model directory (work_dir/output/model-best).

    Raises:
        RuntimeError: If training exits non-zero or times out.
    """
    output_dir = work_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    def _log(msg: str) -> None:
        logger.info("[trainer] %s", msg)
        if log_fn:
            log_fn(msg)

    accelerator = _resolve_training_accelerator()
    use_gpu = accelerator.resolved in {"cuda", "mps"}
    mps_fail_fast = accelerator.resolved == "mps" and os.getenv(
        "TRAINING_MPS_FAIL_FAST", "true"
    ).lower() in ("1", "true", "yes")
    # Honour the configured frozen_components list as-is.  The
    # leo_training.TransformerListener.v1 architecture (see
    # services/training_worker/app/spacy_listener_width.py) explicitly sets the
    # listener's nO dimension so frozen-transformer init no longer requires the
    # transformer to run initialize(). The retry fallback below (attempt 2) still
    # unfreezes on listener-dim error as a belt-and-braces guard.
    frozen_components = [c.strip() for c in _FROZEN.split(",") if c.strip()]
    _log(
        "Starting spaCy training "
        f"(frozen: {','.join(frozen_components) or 'none'}, base: {_HF_MODEL}, gpu: {use_gpu})"
    )
    _log(
        "Accelerator decision "
        f"(requested={accelerator.requested}, resolved={accelerator.resolved}, "
        f"fallback_applied={accelerator.fallback_applied}, "
        f"fallback_reason={accelerator.fallback_reason or 'none'})"
    )
    _log(f"Train: {train_path} | Dev: {dev_path}")

    env = _build_env()
    if accelerator.resolved == "mps":
        env.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    # --- Optional: warm-start from a previously promoted model version -------
    base_version = _BASE_MODEL_VERSION
    init_tok2vec_path: Optional[Path] = None
    if base_version:
        init_tok2vec_path = _fetch_warm_start_model(base_version, _log)

    # --- Attempt 1: primary run (GPU if available) --------------------------
    current_gpu = use_gpu
    returncode, lines = _run_spacy_train(
        work_dir=work_dir,
        output_dir=output_dir,
        train_path=train_path,
        dev_path=dev_path,
        use_gpu=current_gpu,
        env=env,
        log=_log,
        frozen_components=frozen_components,
        config_name="train.cfg",
        init_tok2vec_path=init_tok2vec_path,
        accelerator_resolved=accelerator.resolved,
        seed=seed,
    )

    # --- Attempt 2: unfreeze transformer if listener dim error (before MPS fail-fast)
    # Frozen transformer skips initialize(); listener nO may stay unset unless
    # leo_training.TransformerListener.v1 is used. Retry unfrozen as fallback.
    if (
        returncode != 0
        and _is_transformer_listener_dim_error(lines)
        and "transformer" in frozen_components
    ):
        _log(
            "Detected transformer-listener init error; retrying with transformer unfrozen."
        )
        retry_frozen = [c for c in frozen_components if c != "transformer"]
        returncode, lines = _run_spacy_train(
            work_dir=work_dir,
            output_dir=output_dir,
            train_path=train_path,
            dev_path=dev_path,
            use_gpu=current_gpu,
            env=env,
            log=_log,
            frozen_components=retry_frozen,
            config_name="train_retry_unfrozen.cfg",
            init_tok2vec_path=init_tok2vec_path,
            accelerator_resolved=accelerator.resolved,
            seed=seed,
        )

    # --- Attempt 3: GPU -> CPU fallback --------------------------------------
    if returncode != 0 and current_gpu:
        gpu_runtime_error = _is_gpu_runtime_error(lines)
        recovered_model = _recover_saved_model(output_dir, lines, _log)
        if recovered_model is not None:
            accelerator_meta = {
                "requested_accelerator": accelerator.requested,
                "resolved_accelerator": accelerator.resolved,
                "fallback_applied": accelerator.fallback_applied,
                "fallback_reason": accelerator.fallback_reason,
                "recovered_after_failure": True,
            }
            return recovered_model, accelerator_meta
        if mps_fail_fast and gpu_runtime_error:
            raise RuntimeError(
                "spaCy training failed while running on MPS; fail-fast policy is enabled"
            )
        if gpu_runtime_error:
            _log("Detected GPU runtime error; retrying training on CPU.")
        else:
            _log(
                "Training failed before a GPU runtime error was detected; "
                f"retrying once on CPU for isolation (exit code {returncode})."
            )
        current_gpu = False
        returncode, lines = _run_spacy_train(
            work_dir=work_dir,
            output_dir=output_dir,
            train_path=train_path,
            dev_path=dev_path,
            use_gpu=current_gpu,
            env=env,
            log=_log,
            frozen_components=frozen_components,
            config_name="train_retry_cpu.cfg",
            init_tok2vec_path=init_tok2vec_path,
            accelerator_resolved="cpu",
            seed=seed,
        )

    recovered_model = _recover_saved_model(output_dir, lines, _log)
    if recovered_model is not None:
        accelerator_meta = {
            "requested_accelerator": accelerator.requested,
            "resolved_accelerator": accelerator.resolved,
            "fallback_applied": accelerator.fallback_applied,
            "fallback_reason": accelerator.fallback_reason,
            "recovered_after_failure": True,
        }
        return recovered_model, accelerator_meta

    if returncode != 0:
        raise RuntimeError(f"spaCy training failed with exit code {returncode}")

    model_best = output_dir / "model-best"
    if not model_best.exists():
        model_last = output_dir / "model-last"
        if model_last.exists():
            _log("Warning: model-best not found — using model-last")
            model_best = model_last
        else:
            raise RuntimeError("Training completed but no output model found")

    _log(f"Training complete — model at {model_best}")
    accelerator_meta = {
        "requested_accelerator": accelerator.requested,
        "resolved_accelerator": accelerator.resolved,
        "fallback_applied": accelerator.fallback_applied,
        "fallback_reason": accelerator.fallback_reason,
    }
    return model_best, accelerator_meta


def _write_filled_config(
    out_path: Path,
    *,
    train_path: Path,
    dev_path: Path,
    frozen_components: list[str],
    use_gpu: bool,
    accelerator_resolved: str = "cpu",
    orth_variants_path: Optional[Path] = None,
) -> None:
    """Write a resolved spaCy config with paths and overrides filled in.

    Parameters are always required — callers must resolve them before calling
    so this function never needs to re-derive GPU state or frozen lists.

    Wave 1 additions:
      * TRAINING_WINDOW_TOKENS / TRAINING_STRIDE_TOKENS override the strided
        span getter (F2) without editing base.cfg.
      * mixed_precision is flipped on only when CUDA is the resolved
        accelerator (F5) — MPS and CPU runs do not support PyTorch AMP.
      * TRAINING_LR_SCHEDULE=cosine swaps ``warmup_linear.v1`` for
        ``warmup_cosine.v1`` with matching warmup/total steps (F14).
      * TRAINING_MAX_STEPS overrides ``training.max_steps`` and the LR
        schedule's ``total_steps`` so long local runs can stop at the observed
        plateau without editing the controlled base config.
    """
    config_text = _CONFIG_PATH.read_text(encoding="utf-8")

    frozen_str = json_list(frozen_components)
    # If transformer is frozen, it still needs to run forward passes so
    # TransformerListener layers can infer dimensions from upstream outputs.
    annotating_list = ["transformer"] if "transformer" in frozen_components else []
    annotating_str = json_list(annotating_list)

    config_text = re.sub(
        r"\$\{vars\.hf_model_name\}",
        f'"{_HF_MODEL}"',
        config_text,
    )
    config_text = re.sub(
        r"frozen_components\s*=\s*\[.*?\]",
        f"frozen_components = {frozen_str}",
        config_text,
    )
    config_text = re.sub(
        r"annotating_components\s*=\s*\[.*?\]",
        f"annotating_components = {annotating_str}",
        config_text,
    )
    config_text = _apply_ablation_profile(config_text)

    # F2: window/stride overrides.
    window = _env_int("TRAINING_WINDOW_TOKENS", 0)
    if window > 0:
        config_text = re.sub(
            r"(?m)^window\s*=\s*\d+",
            f"window = {window}",
            config_text,
            count=1,
        )
    stride = _env_int("TRAINING_STRIDE_TOKENS", 0)
    if stride > 0:
        config_text = re.sub(
            r"(?m)^stride\s*=\s*\d+",
            f"stride = {stride}",
            config_text,
            count=1,
        )

    if use_gpu:
        config_text = re.sub(
            r"gpu_allocator\s*=\s*null",
            'gpu_allocator = "pytorch"',
            config_text,
        )

    # F5: AMP only on CUDA.  PyTorch MPS has partial AMP support and tends to
    # produce NaNs on the spancat head; CPU gains nothing.
    if accelerator_resolved == "cuda":
        config_text = re.sub(
            r"(?m)^mixed_precision\s*=\s*false",
            "mixed_precision = true",
            config_text,
            count=1,
        )

    max_steps = _env_int("TRAINING_MAX_STEPS", 0)
    if max_steps > 0:
        config_text = re.sub(
            r"(?m)^max_steps\s*=\s*\d+",
            f"max_steps = {max_steps}",
            config_text,
            count=1,
        )
        config_text = re.sub(
            r"(?m)^total_steps\s*=\s*\d+",
            f"total_steps = {max_steps}",
            config_text,
            count=1,
        )

    # F14: cosine schedule opt-in.
    if _resolve_lr_schedule() == "cosine":
        config_text = re.sub(
            r'(?m)^@schedules\s*=\s*"warmup_linear\.v1"',
            '@schedules = "warmup_cosine.v1"',
            config_text,
            count=1,
        )

    # Wave 2 (F8): if no orth_variants table is available, strip the
    # [corpora.train.augmenter] block so spaCy does not fail resolving the
    # null path reference.
    if orth_variants_path is None or not orth_variants_path.exists():
        config_text = _strip_augmenter_section(config_text)

    out_path.write_text(config_text, encoding="utf-8")


def _strip_augmenter_section(config_text: str) -> str:
    """Remove ``[corpora.train.augmenter...]`` blocks; re-set augmenter to null.

    Works in multiline (not single-line) mode so ``.*`` stays within a line and
    the section end is anchored by the next top-level ``[section]`` header.
    """
    lines = config_text.splitlines(keepends=True)
    out: list[str] = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[corpora.train.augmenter"):
            skip = True
            continue
        if skip:
            if stripped.startswith("[") and stripped.endswith("]"):
                skip = False
                # Fall through to append this header line.
            else:
                continue
        out.append(line)
    cleaned = "".join(out)

    # Ensure [corpora.train] has an `augmenter = null` line so spaCy does not
    # try to resolve the (now removed) ${paths.orth_variants}.
    train_header = "[corpora.train]"
    dev_header = "[corpora.dev]"
    train_idx = cleaned.find(train_header)
    dev_idx = cleaned.find(dev_header)
    if train_idx != -1 and dev_idx != -1 and dev_idx > train_idx:
        section = cleaned[train_idx:dev_idx]
        if not re.search(r"(?m)^augmenter\s*=", section):
            section = section.rstrip() + "\naugmenter = null\n\n"
            cleaned = cleaned[:train_idx] + section + cleaned[dev_idx:]
    return cleaned


def json_list(items: list[str]) -> str:
    return "[" + ", ".join(f'"{i}"' for i in items) + "]"


def _is_transformer_listener_dim_error(lines: list[str]) -> bool:
    for line in lines:
        low = line.lower()
        if "transformer-listener" in low and "dimension" in low and "unset" in low:
            return True
        if "transformer-listener" in low and "no" in low and "get_dim" in low:
            return True
    return False


def _is_gpu_runtime_error(lines: list[str]) -> bool:
    for line in lines:
        low = line.lower()
        if "from_dlpack" in low and "invalid capsule" in low:
            return True
        if "dlpack" in low and "consumed only once" in low:
            return True
        if "cupy" in low and "cuda" in low and "error" in low:
            return True
        if "mps" in low and ("error" in low or "unsupported" in low or "failed" in low):
            return True
        if "metal" in low and ("error" in low or "failed" in low):
            return True
    return False


def _recover_saved_model(
    output_dir: Path,
    lines: list[str],
    log: Callable[[str], None],
) -> Optional[Path]:
    """Return a saved checkpoint if spaCy aborted after writing one."""
    joined = "\n".join(lines).lower()
    saved_after_abort = "aborting and saving the final best model" in joined
    saved_after_timeout = (
        "wall-clock training timeout" in joined or "wall-clock limit" in joined
    )
    if not saved_after_abort and not saved_after_timeout:
        return None

    model_best = output_dir / "model-best"
    if model_best.exists():
        log(
            "spaCy aborted after saving checkpoints; recovering model-best "
            f"from {model_best}."
        )
        return model_best

    model_last = output_dir / "model-last"
    if model_last.exists():
        log(
            "spaCy aborted after saving checkpoints; model-best missing, "
            f"recovering model-last from {model_last}."
        )
        return model_last
    return None


def _run_spacy_train(
    *,
    work_dir: Path,
    output_dir: Path,
    train_path: Path,
    dev_path: Path,
    use_gpu: bool,
    env: dict,
    log: Callable[[str], None],
    frozen_components: list[str],
    config_name: str,
    init_tok2vec_path: Optional[Path] = None,
    accelerator_resolved: str = "cpu",
    seed: Optional[int] = None,
) -> tuple[int, list[str]]:
    filled_config = work_dir / config_name
    orth_variants_candidate = train_path.parent / "orth_variants.json"
    _write_filled_config(
        filled_config,
        train_path=train_path,
        dev_path=dev_path,
        frozen_components=frozen_components,
        use_gpu=use_gpu,
        accelerator_resolved=accelerator_resolved,
        orth_variants_path=(
            orth_variants_candidate if orth_variants_candidate.exists() else None
        ),
    )
    cmd = [
        sys.executable,
        "-u",
        "-m",
        "app.run_spacy_train_cli",
        "train",
        str(filled_config),
        "--output",
        str(output_dir),
        "--paths.train",
        str(train_path),
        "--paths.dev",
        str(dev_path),
    ]
    orth_variants_path = train_path.parent / "orth_variants.json"
    if orth_variants_path.exists():
        cmd.extend(["--paths.orth_variants", str(orth_variants_path)])
    if use_gpu:
        cmd.extend(["--gpu-id", "0"])
    if init_tok2vec_path is not None and init_tok2vec_path.exists():
        cmd.extend(["--initialize.init_tok2vec", str(init_tok2vec_path)])
    if seed is not None:
        cmd.extend(["--system.seed", str(seed)])

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        cwd=_TRAINING_APP_ROOT,
    )
    wall_s = _parse_training_wall_timeout_s()
    wall_timeout = threading.Event()

    def _wall_clock_watchdog() -> None:
        if wall_s <= 0:
            return
        time.sleep(wall_s)
        if proc.poll() is not None:
            return
        wall_timeout.set()
        log(
            f"Wall-clock training timeout after {wall_s}s (TRAINING_JOB_TIMEOUT_S) "
            f"— terminating subprocess. Set to 0 to disable."
        )
        try:
            proc.kill()
        except OSError as exc:  # pragma: no cover
            logger.warning("Could not kill training subprocess: %s", exc)

    if wall_s > 0:
        threading.Thread(
            target=_wall_clock_watchdog,
            name="training-wall-timeout",
            daemon=True,
        ).start()

    lines: list[str] = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                lines.append(line)
                log(line)
    finally:
        try:
            if proc.poll() is None:
                proc.wait(timeout=120.0)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError as exc:  # pragma: no cover
                logger.warning("Could not kill stuck training subprocess: %s", exc)
            try:
                proc.wait(timeout=30.0)
            except subprocess.TimeoutExpired:  # pragma: no cover
                logger.warning("Training subprocess did not exit after kill")

    if wall_timeout.is_set():
        timeout_message = (
            f"Training exceeded wall-clock limit of {wall_s}s (TRAINING_JOB_TIMEOUT_S). "
            f"Recovering a saved checkpoint if one exists."
        )
        lines.append(timeout_message)
        log(timeout_message)
        recovered = _recover_saved_model(output_dir, lines, log)
        if recovered is not None:
            return 0, lines
        raise RuntimeError(
            f"Training exceeded wall-clock limit of {wall_s}s (TRAINING_JOB_TIMEOUT_S). "
            f"Increase the variable or set it to 0 to disable the cap."
        )
    return proc.returncode or 0, lines
