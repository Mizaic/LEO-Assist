#!/usr/bin/env python3
"""Validate pilot traceability coverage for selected design inputs."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

DEFAULT_DI_IDS = [
    "DI-LEO-AI-018",
    "DI-LEO-AI-019",
    "DI-LEO-AI-094",
    "DI-LEO-AI-095",
    "DI-LEO-AI-099",
]


_ID_RE = re.compile(r'^\s*-\s+id:\s*"?(?P<id>[A-Z]+-LEO-AI-\d+)"?\s*$', re.MULTILINE)
_SAFETY_RE = re.compile(r'^\s*safety_class:\s*"?(?P<value>[ABC])"?\s*$', re.MULTILINE)
_RISKS_INLINE_RE = re.compile(r"^\s*risks:\s*\[(?P<items>[^\]]*)\]\s*$", re.MULTILINE)
_TEST_PROTOCOL_RE = re.compile(
    r'^\s*test_protocol:\s*"?(?P<vt>VT-LEO-AI-\d+)"?\s*$',
    re.MULTILINE,
)
_DO_DESIGN_INPUTS_RE = re.compile(
    r"^\s*design_inputs:\s*\[(?P<items>[^\]]*)\]\s*$",
    re.MULTILINE,
)
_VT_STATUS_RE = re.compile(
    r'^\s*status:\s*"?(?P<status>[a-zA-Z_]+)"?\s*$', re.MULTILINE
)
_VT_PASS_RE = re.compile(r'^\s*result:\s*"?(?P<result>pass)"?\s*$', re.MULTILINE)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_inline_list(raw_items: str) -> list[str]:
    values: list[str] = []
    for token in raw_items.split(","):
        value = token.strip().strip('"').strip("'")
        if value:
            values.append(value)
    return values


def _extract_first(pattern: re.Pattern[str], text: str, key: str) -> str:
    match = pattern.search(text)
    if not match:
        return ""
    return str(match.group(key)).strip()


def _build_do_index(design_outputs_dir: Path) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for file_path in sorted(design_outputs_dir.glob("DO-LEO-AI-*.yaml")):
        text = _read(file_path)
        do_id = _extract_first(_ID_RE, text, "id") or file_path.stem
        di_items = _extract_first(_DO_DESIGN_INPUTS_RE, text, "items")
        for di_id in _parse_inline_list(di_items):
            index.setdefault(di_id, []).append(do_id)
    return index


def _vt_file_for_id(vt_dir: Path, vt_id: str) -> Path:
    return vt_dir / f"{vt_id}.yaml"


def _has_non_empty_risks(di_text: str) -> bool:
    risks_inline = _extract_first(_RISKS_INLINE_RE, di_text, "items")
    if not risks_inline:
        return False
    return any(
        item.startswith("R-LEO-AI-") for item in _parse_inline_list(risks_inline)
    )


def validate(repo_root: Path, di_ids: list[str], waived_di_ids: set[str]) -> int:
    di_dir = repo_root / "design-controls" / "design-inputs"
    vt_dir = repo_root / "design-controls" / "verification-tests"
    do_index = _build_do_index(repo_root / "design-controls" / "design-outputs")

    failures: list[str] = []
    warnings: list[str] = []

    for di_id in di_ids:
        di_file = di_dir / f"{di_id}.yaml"
        if not di_file.exists():
            failures.append(f"{di_id}: missing design input file")
            continue

        di_text = _read(di_file)
        safety_class = _extract_first(_SAFETY_RE, di_text, "value")
        vt_id = _extract_first(_TEST_PROTOCOL_RE, di_text, "vt")
        linked_dos = do_index.get(di_id, [])

        if not linked_dos:
            failures.append(f"{di_id}: no linked design output references this DI")

        if safety_class in {"B", "C"} and not _has_non_empty_risks(di_text):
            failures.append(f"{di_id}: safety class {safety_class} with empty risks")

        if not vt_id:
            failures.append(f"{di_id}: missing verification.test_protocol")
            continue

        vt_file = _vt_file_for_id(vt_dir, vt_id)
        if not vt_file.exists():
            failures.append(f"{di_id}: referenced VT missing ({vt_id})")
            continue

        vt_text = _read(vt_file)
        vt_status = _extract_first(_VT_STATUS_RE, vt_text, "status").lower()
        has_pass = bool(_VT_PASS_RE.search(vt_text))
        has_history_section = "execution_history:" in vt_text
        if vt_status != "passed":
            warnings.append(
                f"{di_id}: VT {vt_id} status is {vt_status!r}, expected 'passed'"
            )
        if not has_history_section or not has_pass:
            if di_id in waived_di_ids:
                warnings.append(
                    f"{di_id}: VT {vt_id} has no passing run yet (waived for this check)"
                )
                continue
            failures.append(
                f"{di_id}: VT {vt_id} lacks passing execution history evidence"
            )

    if warnings:
        print("Pilot traceability warnings:")
        for item in warnings:
            print(f"- {item}")

    if failures:
        print("Pilot traceability check FAILED")
        for item in failures:
            print(f"- {item}")
        return 1

    print("Pilot traceability check PASSED")
    for di_id in di_ids:
        print(f"- {di_id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Path to repository root (default: current directory)",
    )
    parser.add_argument(
        "--di-id",
        action="append",
        dest="di_ids",
        help="Design input ID to check. Repeat for multiple IDs.",
    )
    parser.add_argument(
        "--waive-di",
        action="append",
        dest="waived_di_ids",
        help="Design input ID to waive when no passing VT evidence exists.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    di_ids = args.di_ids or DEFAULT_DI_IDS
    waived_di_ids = set(args.waived_di_ids or [])
    return validate(repo_root=repo_root, di_ids=di_ids, waived_di_ids=waived_di_ids)


if __name__ == "__main__":
    sys.exit(main())
