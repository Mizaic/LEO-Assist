#!/usr/bin/env python3
"""Detect which container images CI should rebuild from a git diff.

Outputs GitHub Actions outputs:
  services      - JSON matrix include list for backend image builds
  build_ui      - "true" / "false"
  has_backend   - "true" / "false"
  build_all     - "true" / "false"
  services_csv  - comma-separated service names (includes ui when selected)

Atlas trace:
  DO: DO-6036D724
  DI: DI-71087A9E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-6036D724")
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BACKEND_SERVICES: list[dict[str, str]] = [
    {
        "service": "core-api",
        "dockerfile": "infra/dockerfiles/Dockerfile.core-api",
    },
    {
        "service": "terminology-api",
        "dockerfile": "infra/dockerfiles/Dockerfile.terminology-api",
    },
    {
        "service": "fhir-api",
        "dockerfile": "infra/dockerfiles/Dockerfile.fhir-api",
    },
    {
        "service": "analytics-api",
        "dockerfile": "infra/dockerfiles/Dockerfile.analytics-api",
    },
    {
        "service": "pipeline-worker",
        "dockerfile": "infra/dockerfiles/Dockerfile.pipeline-worker",
    },
    {
        "service": "model-inference",
        "dockerfile": "infra/dockerfiles/Dockerfile.model-inference",
    },
    {
        "service": "training-worker",
        "dockerfile": "infra/dockerfiles/Dockerfile.training-worker",
    },
    {
        "service": "research-worker",
        "dockerfile": "infra/dockerfiles/Dockerfile.research-worker",
    },
]

# Shared paths that invalidate every image (libs are COPY'd into all Python images).
BLAST_RADIUS_PREFIXES = (
    "libs/",
    "requirements.txt",
    "requirements-dev.txt",
    ".github/workflows/ci-build.yml",
    "scripts/ci/detect_changed_services.py",
)

# Path ownership derived from infra/dockerfiles/Dockerfile.* COPY lines.
SERVICE_PATHS: dict[str, tuple[str, ...]] = {
    "core-api": (
        "services/api/",
        "services/coding_worker/",
        "services/terminology_api/",
        "scripts/",
        "tests/fixtures/clinical_extraction_scenarios/",
        "infra/dockerfiles/Dockerfile.core-api",
    ),
    "terminology-api": (
        "services/terminology_api/",
        "infra/dockerfiles/Dockerfile.terminology-api",
    ),
    "fhir-api": (
        "services/fhir_api/",
        "scripts/",
        "infra/dockerfiles/Dockerfile.fhir-api",
    ),
    "analytics-api": (
        "services/analytics_api/",
        "services/analysis_worker/",
        "configs/snomed/",
        "infra/dockerfiles/Dockerfile.analytics-api",
    ),
    "pipeline-worker": (
        "services/pipeline_worker/",
        "services/coding_worker/",
        "services/analysis_worker/",
        "services/terminology_api/",
        "infra/dockerfiles/Dockerfile.pipeline-worker",
    ),
    "model-inference": (
        "services/model_inference/",
        "infra/dockerfiles/Dockerfile.model-inference",
    ),
    "training-worker": (
        "services/training_worker/",
        "infra/dockerfiles/Dockerfile.training-worker",
    ),
    "research-worker": (
        "services/research_worker/",
        "services/analytics_api/",
        "infra/dockerfiles/Dockerfile.research-worker",
    ),
    "ui": (
        "services/ui/",
        "services/design-system/",
        "services/widget-sdk/",
        "package.json",
        "package-lock.json",
        "infra/dockerfiles/Dockerfile.ui",
    ),
}

KNOWN_DOCKERFILES = {s["dockerfile"] for s in BACKEND_SERVICES} | {
    "infra/dockerfiles/Dockerfile.ui",
}


def git_changed_files(base: str, head: str) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        proc = subprocess.run(
            ["git", "diff", "--name-only", base, head],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def matches_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    for prefix in prefixes:
        if path == prefix or path.startswith(prefix):
            return True
    return False


def detect(
    changed: list[str],
    *,
    force_all: bool,
) -> tuple[list[dict[str, str]], bool, bool]:
    """Return (backend_matrix, build_ui, build_all)."""
    if force_all:
        return list(BACKEND_SERVICES), True, True

    if any(matches_prefix(path, BLAST_RADIUS_PREFIXES) for path in changed):
        return list(BACKEND_SERVICES), True, True

    for path in changed:
        if path.startswith("infra/dockerfiles/") and path not in KNOWN_DOCKERFILES:
            return list(BACKEND_SERVICES), True, True

    selected: set[str] = set()
    for path in changed:
        for service, prefixes in SERVICE_PATHS.items():
            if matches_prefix(path, prefixes):
                selected.add(service)

    build_ui = "ui" in selected
    backend = [row for row in BACKEND_SERVICES if row["service"] in selected]
    return backend, build_ui, False


def write_output(name: str, value: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")
    print(f"{name}={value}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument(
        "--force-all",
        action="store_true",
        help="Rebuild every image (schedule / dispatch)",
    )
    args = ap.parse_args()

    changed: list[str] = []
    if not args.force_all:
        if not args.base:
            print("ERROR: --base is required unless --force-all", file=sys.stderr)
            return 2
        changed = git_changed_files(args.base, args.head)
        print(f"Changed files ({len(changed)}):")
        for path in changed[:80]:
            print(f"  {path}")
        if len(changed) > 80:
            print(f"  ... and {len(changed) - 80} more")

    backend, build_ui, build_all = detect(changed, force_all=args.force_all)
    names = [row["service"] for row in backend]
    if build_ui:
        names.append("ui")

    write_output("services", json.dumps(backend))
    write_output("build_ui", "true" if build_ui else "false")
    write_output("has_backend", "true" if backend else "false")
    write_output("build_all", "true" if build_all else "false")
    write_output("services_csv", ",".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
