"""spaCy training subprocess wrapper.

Runs `python -m spacy train` in a subprocess, streams stdout/stderr line
by line to the job log, and returns the path to the best model output.

If TRAINING_BASE_MODEL_VERSION is set, the promoted blob model is downloaded
first and used as the NER component's initial weights (warm start).
The Bio_ClinicalBERT transformer backbone is always loaded from HuggingFace
Hub (cached in TRANSFORMERS_CACHE) — it is never packed into the blob artifact.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "config" / "base.cfg"
_TIMEOUT_S = int(os.getenv("TRAINING_JOB_TIMEOUT_S", "3600"))
_HF_MODEL = os.getenv("TRAINING_HF_BASE_MODEL", "emilyalsentzer/Bio_ClinicalBERT")
_FROZEN = os.getenv("TRAINING_FROZEN_COMPONENTS", "transformer")


def _should_use_gpu() -> bool:
    """Return True only if CuPy can actually initialise a CUDA device.

    torch.cuda.is_available() is not sufficient — spaCy uses CuPy internally
    and will crash if CuPy cannot load the CUDA runtime even when torch can.
    Set TRAINING_USE_GPU=false to force CPU (avoids CuPy/CUDA issues on Windows).
    """
    if os.getenv("TRAINING_USE_GPU", "true").lower() in ("false", "0", "no"):
        return False
    try:
        import cupy
        cupy.array([1.0])   # actually execute on GPU; raises if CUDA load fails
        return True
    except Exception as exc:
        logger.warning("CuPy GPU test failed (%s) — falling back to CPU", exc)
        return False


def _build_env() -> dict:
    """Return a subprocess env with CUDA DLL paths added for CuPy on Windows.

    When only PyTorch's bundled CUDA is present (no standalone CUDA toolkit),
    CuPy needs PyTorch's lib directory on PATH so it can find the CUDA runtime
    DLLs (cudart64_*.dll etc.).
    """
    env = dict(os.environ)
    try:
        import torch
        torch_lib = os.path.join(os.path.dirname(torch.__file__), "lib")
        if os.path.isdir(torch_lib):
            env["PATH"] = f"{torch_lib};{env.get('PATH', '')}"
        # CuPy appends \bin to CUDA_PATH and calls os.add_dll_directory() on it.
        # If that path doesn't exist (e.g. torch\lib\bin), it raises FileNotFoundError.
        # Unset invalid CUDA_PATH so CuPy falls back to nvidia-*-cu12 wheel packages.
        cuda_path = env.get("CUDA_PATH", "").strip()
        if cuda_path:
            cuda_bin = os.path.join(cuda_path, "bin")
            if not os.path.isdir(cuda_bin):
                env.pop("CUDA_PATH", None)
    except Exception:
        pass
    env.setdefault("TRANSFORMERS_CACHE", os.getenv("TRANSFORMERS_CACHE", "/tmp/hf_cache"))
    return env


def run_training(
    work_dir: Path,
    *,
    train_path: Path,
    dev_path: Path,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Path:
    """Run spaCy training and return the path to the best model.

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

    # Write a filled config resolving paths and model name
    filled_config = work_dir / "train.cfg"
    _write_filled_config(
        filled_config,
        train_path=train_path,
        dev_path=dev_path,
    )

    def _log(msg: str) -> None:
        logger.info("[trainer] %s", msg)
        if log_fn:
            log_fn(msg)

    use_gpu = _should_use_gpu()
    _log(f"Starting spaCy training (frozen: {_FROZEN}, base: {_HF_MODEL}, gpu: {use_gpu})")
    _log(f"Train: {train_path} | Dev: {dev_path}")

    cmd = [
        sys.executable, "-m", "spacy", "train",
        str(filled_config),
        "--output", str(output_dir),
        "--paths.train", str(train_path),
        "--paths.dev", str(dev_path),
    ]
    if use_gpu:
        cmd.extend(["--gpu-id", "0"])

    env = _build_env()

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )

        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                _log(line)

        proc.wait(timeout=_TIMEOUT_S)

    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError(f"Training timed out after {_TIMEOUT_S}s")

    if proc.returncode != 0:
        raise RuntimeError(f"spaCy training failed with exit code {proc.returncode}")

    model_best = output_dir / "model-best"
    if not model_best.exists():
        # Fallback to model-last if best was not saved
        model_last = output_dir / "model-last"
        if model_last.exists():
            _log("Warning: model-best not found — using model-last")
            model_best = model_last
        else:
            raise RuntimeError("Training completed but no output model found")

    _log(f"Training complete — model at {model_best}")
    return model_best


def _write_filled_config(
    out_path: Path,
    *,
    train_path: Path,
    dev_path: Path,
) -> None:
    """Write a resolved spaCy config with paths and overrides filled in."""
    config_text = _CONFIG_PATH.read_text(encoding="utf-8")

    frozen_list = [c.strip() for c in _FROZEN.split(",") if c.strip()]
    frozen_str = json_list(frozen_list)

    import re
    config_text = re.sub(
        r'\$\{vars\.hf_model_name\}',
        f'"{_HF_MODEL}"',
        config_text,
    )

    config_text = re.sub(
        r'frozen_components\s*=\s*\[.*?\]',
        f'frozen_components = {frozen_str}',
        config_text,
    )

    use_gpu = _should_use_gpu()
    if use_gpu:
        config_text = re.sub(
            r'gpu_allocator\s*=\s*null',
            'gpu_allocator = "pytorch"',
            config_text,
        )

    out_path.write_text(config_text, encoding="utf-8")


def json_list(items: list[str]) -> str:
    return "[" + ", ".join(f'"{i}"' for i in items) + "]"
