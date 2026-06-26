#!/usr/bin/env python3
"""Restore '#' characters corrupted as '***REMOVED***' in the working tree.

Context: a mistaken bulk redaction (likely git-filter-repo --replace-text) replaced
every '#' with the literal string '***REMOVED***' across repo history.

This script reverses that corruption in the current checkout only. It does NOT
rewrite git history. For history repair, restore from a clean clone or run
git-filter-repo with literal:***REMOVED***==># after backing up the remote.

Usage:
  python scripts/compliance/restore-hash-from-removed.py           # dry run
  python scripts/compliance/restore-hash-from-removed.py --execute # apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Avoid embedding the needle as a contiguous literal so this file is safe to process.
NEEDLE = "***" + "REMOVED" + "***"
REPLACEMENT = "#"
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__"}
SKIP_FILES = {"restore-hash-from-removed.py"}


def should_skip(path: Path) -> bool:
    if path.name in SKIP_FILES:
        return True
    return any(part in SKIP_DIRS for part in path.parts)


def scan_repo(root: Path) -> list[tuple[Path, int]]:
    hits: list[tuple[Path, int]] = []
    for path in root.rglob("*"):
        if not path.is_file() or should_skip(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        count = text.count(NEEDLE)
        if count:
            hits.append((path, count))
    return hits


def apply(hits: list[tuple[Path, int]]) -> int:
    total = 0
    for path, _ in hits:
        text = path.read_text(encoding="utf-8")
        new_text = text.replace(NEEDLE, REPLACEMENT)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            total += text.count(NEEDLE)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore # from corrupted marker")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write changes (default is dry run)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    hits = scan_repo(root)
    occurrences = sum(c for _, c in hits)
    print(f"Repository: {root}")
    print(f"Affected files: {len(hits)}")
    print(f"Occurrences of {NEEDLE}: {occurrences}")

    if not hits:
        print("Nothing to restore.")
        return 0

    if not args.execute:
        print("\nDry run only. Re-run with --execute to apply.")
        print("Top 15 files by occurrence count:")
        for path, count in sorted(hits, key=lambda x: -x[1])[:15]:
            print(f"  {count:5d}  {path.relative_to(root)}")
        return 0

    replaced = apply(hits)
    remaining = sum(c for _, c in scan_repo(root))
    print(f"\nReplaced {replaced} occurrence(s).")
    print(f"Remaining {NEEDLE} in tree: {remaining}")
    return 0 if remaining == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
