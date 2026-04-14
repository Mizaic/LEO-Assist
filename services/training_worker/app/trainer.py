"""spaCy training subprocess wrapper.

Runs ``python -m app.run_spacy_train_cli train`` (registers ``leo_training.TransformerListener``)
in a subprocess, streams stdout/stderr line
by line to the job log, and returns the path to the best model output.

If TRAINING_BASE_MODEL_VERSION is set, the promoted blob model is downloaded
first and used as the NER component's initial weights (warm start).
The Bio_ClinicalBERT transformer backbone is always loaded from HuggingFace
Hub (cached in HF_HOME) — it is never packed into the blob artifact.
"""

from __future__ import annotations

import glob as _glob
import logging
import os
import re
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Callable, Optional

from libs.utils.device_resolver import AcceleratorDecision, resolve_accelerator

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "config" / "base.cfg"
_TRAINING_APP_ROOT = Path(__file__).resolve().parents[1]
_TIMEOUT_S = int(os.getenv("TRAINING_JOB_TIMEOUT_S", "3600"))
_HF_MODEL = os.getenv("TRAINING_HF_BASE_MODEL", "emilyalsentzer/Bio_ClinicalBERT")
_FROZEN = os.getenv("TRAINING_FROZEN_COMPONENTS", "transformer")
_BASE_MODEL_VERSION = os.getenv("TRAINING_BASE_MODEL_VERSION", "").strip()


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


def run_training(
    work_dir: Path,
    *,
    train_path: Path,
    dev_path: Path,
    log_fn: Optional[Callable[[str], None]] = None,
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
    frozen_components = [c.strip() for c in _FROZEN.split(",") if c.strip()]
    if "transformer" in frozen_components:
        frozen_components = [c for c in frozen_components if c != "transformer"]
        _log(
            "Transformer freeze disabled. This training path starts from the "
            "Bio_ClinicalBERT HF checkpoint, so the transformer must initialize "
            "its tokenizer/model before training. Freezing it here leaves the "
            "tokenizer unset and causes spaCy to fail at runtime."
        )
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
) -> None:
    """Write a resolved spaCy config with paths and overrides filled in.

    Parameters are always required — callers must resolve them before calling
    so this function never needs to re-derive GPU state or frozen lists.
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

    if use_gpu:
        config_text = re.sub(
            r"gpu_allocator\s*=\s*null",
            'gpu_allocator = "pytorch"',
            config_text,
        )

    out_path.write_text(config_text, encoding="utf-8")


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
    if "aborting and saving the final best model" not in joined:
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
) -> tuple[int, list[str]]:
    filled_config = work_dir / config_name
    _write_filled_config(
        filled_config,
        train_path=train_path,
        dev_path=dev_path,
        frozen_components=frozen_components,
        use_gpu=use_gpu,
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
    if use_gpu:
        cmd.extend(["--gpu-id", "0"])
    if init_tok2vec_path is not None and init_tok2vec_path.exists():
        cmd.extend(["--initialize.init_tok2vec", str(init_tok2vec_path)])

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        cwd=_TRAINING_APP_ROOT,
    )
    lines: list[str] = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                lines.append(line)
                log(line)
        proc.wait(timeout=_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError(f"Training timed out after {_TIMEOUT_S}s")
    return proc.returncode or 0, lines
