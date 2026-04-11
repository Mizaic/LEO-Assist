"""Shared accelerator resolution and preflight probes.

Supports CPU, CUDA, and Apple MPS with safe startup-time fallback behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
import platform
from typing import Literal

Accelerator = Literal["auto", "cpu", "cuda", "mps"]
ResolvedAccelerator = Literal["cpu", "cuda", "mps"]


@dataclass(frozen=True)
class AcceleratorDecision:
    """Resolved accelerator with provenance for logging/telemetry."""

    requested: Accelerator
    resolved: ResolvedAccelerator
    fallback_applied: bool
    fallback_reason: str
    platform_name: str
    machine: str
    macos_major: int | None


def resolve_accelerator(
    requested: str | None,
    *,
    prefer_mps_on_macos: bool = True,
    min_macos_major_for_mps: int = 26,
    enforce_apple_silicon_for_mps: bool = True,
) -> AcceleratorDecision:
    """Resolve requested accelerator to an available backend.

    Rules:
      - `cpu` always resolves to CPU.
      - `cuda` resolves to CUDA only when probe succeeds; otherwise CPU fallback.
      - `mps` resolves to MPS only when probe succeeds; otherwise CPU fallback.
      - `auto` prefers:
          - macOS: MPS (when enabled) -> CPU
          - non-macOS: CUDA -> CPU
    """
    req = _normalise_requested(requested)
    platform_name = platform.system().lower()
    machine = platform.machine().lower()
    mac_major = _macos_major_version()

    if req == "cpu":
        return AcceleratorDecision(
            requested=req,
            resolved="cpu",
            fallback_applied=False,
            fallback_reason="",
            platform_name=platform_name,
            machine=machine,
            macos_major=mac_major,
        )

    if req == "cuda":
        ok, reason = _probe_cuda()
        return _decision_from_probe(
            requested=req,
            candidate="cuda",
            ok=ok,
            reason=reason,
            platform_name=platform_name,
            machine=machine,
            macos_major=mac_major,
        )

    if req == "mps":
        ok, reason = _probe_mps(
            min_macos_major_for_mps=min_macos_major_for_mps,
            enforce_apple_silicon_for_mps=enforce_apple_silicon_for_mps,
        )
        return _decision_from_probe(
            requested=req,
            candidate="mps",
            ok=ok,
            reason=reason,
            platform_name=platform_name,
            machine=machine,
            macos_major=mac_major,
        )

    # auto
    if platform_name == "darwin" and prefer_mps_on_macos:
        ok, reason = _probe_mps(
            min_macos_major_for_mps=min_macos_major_for_mps,
            enforce_apple_silicon_for_mps=enforce_apple_silicon_for_mps,
        )
        if ok:
            return AcceleratorDecision(
                requested=req,
                resolved="mps",
                fallback_applied=False,
                fallback_reason="",
                platform_name=platform_name,
                machine=machine,
                macos_major=mac_major,
            )
        return AcceleratorDecision(
            requested=req,
            resolved="cpu",
            fallback_applied=True,
            fallback_reason=reason,
            platform_name=platform_name,
            machine=machine,
            macos_major=mac_major,
        )

    ok, reason = _probe_cuda()
    if ok:
        return AcceleratorDecision(
            requested=req,
            resolved="cuda",
            fallback_applied=False,
            fallback_reason="",
            platform_name=platform_name,
            machine=machine,
            macos_major=mac_major,
        )
    return AcceleratorDecision(
        requested=req,
        resolved="cpu",
        fallback_applied=True,
        fallback_reason=reason,
        platform_name=platform_name,
        machine=machine,
        macos_major=mac_major,
    )


def _decision_from_probe(
    *,
    requested: Accelerator,
    candidate: ResolvedAccelerator,
    ok: bool,
    reason: str,
    platform_name: str,
    machine: str,
    macos_major: int | None,
) -> AcceleratorDecision:
    if ok:
        return AcceleratorDecision(
            requested=requested,
            resolved=candidate,
            fallback_applied=False,
            fallback_reason="",
            platform_name=platform_name,
            machine=machine,
            macos_major=macos_major,
        )
    return AcceleratorDecision(
        requested=requested,
        resolved="cpu",
        fallback_applied=True,
        fallback_reason=reason,
        platform_name=platform_name,
        machine=machine,
        macos_major=macos_major,
    )


def _normalise_requested(requested: str | None) -> Accelerator:
    raw = (requested or "auto").strip().lower()
    if raw in {"auto", "cpu", "cuda", "mps"}:
        return raw  # type: ignore[return-value]
    return "auto"


def _macos_major_version() -> int | None:
    if platform.system().lower() != "darwin":
        return None
    ver = platform.mac_ver()[0]
    if not ver:
        return None
    first = ver.split(".", 1)[0].strip()
    if not first.isdigit():
        return None
    return int(first)


def _probe_cuda() -> tuple[bool, str]:
    try:
        import torch
    except Exception as exc:
        return False, f"torch unavailable: {type(exc).__name__}"
    try:
        if not torch.cuda.is_available():
            return False, "torch.cuda.is_available() is False"
        # Tiny op to prove runtime is truly usable.
        tensor = torch.tensor([1.0], device="cuda")
        _ = float(tensor.sum().item())
        return True, ""
    except Exception as exc:
        return False, f"cuda preflight failed: {type(exc).__name__}: {exc}"


def _probe_mps(
    *,
    min_macos_major_for_mps: int,
    enforce_apple_silicon_for_mps: bool,
) -> tuple[bool, str]:
    if platform.system().lower() != "darwin":
        return False, "mps unsupported: host is not macOS"

    if enforce_apple_silicon_for_mps:
        machine = platform.machine().lower()
        if machine not in {"arm64", "arm64e"}:
            return False, f"mps unsupported: machine={machine} is not Apple Silicon"

    mac_major = _macos_major_version()
    if mac_major is None:
        return False, "mps unsupported: unable to read macOS version"
    if mac_major < min_macos_major_for_mps:
        return False, (
            f"mps disabled: macOS {mac_major} is below required {min_macos_major_for_mps}"
        )

    try:
        import torch
    except Exception as exc:
        return False, f"torch unavailable: {type(exc).__name__}"

    try:
        mps_backend = getattr(torch.backends, "mps", None)
        if mps_backend is None:
            return False, "torch.backends.mps is unavailable"
        if not mps_backend.is_built():
            return False, "torch MPS backend is not built in this wheel"
        if not mps_backend.is_available():
            return False, "torch.backends.mps.is_available() is False"
        # Tiny op to verify runtime path.
        tensor = torch.tensor([1.0], device="mps")
        _ = float(tensor.sum().item())
        return True, ""
    except Exception as exc:
        return False, f"mps preflight failed: {type(exc).__name__}: {exc}"

