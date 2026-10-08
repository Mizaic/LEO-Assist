#!/usr/bin/env python3
"""Build an Azure Container Registry tag from a commit and branch name.

Atlas trace:
  DO: DO-6036D724
  DI: DI-71087A9E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-6036D724")
"""

from __future__ import annotations

import os
import sys

MAX_TAG_LENGTH = 128
_HEX = set("0123456789abcdefABCDEF")
_SAFE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")
_SPACE = set(" \t\n\r\f\v/")


def sanitize_branch(ref_name: str) -> str:
    """Turn a git branch name into characters a registry tag allows."""
    cleaned = []
    for char in ref_name:
        if char in _SPACE or char not in _SAFE:
            cleaned.append("_")
        else:
            cleaned.append(char)
    return "".join(cleaned)


def build_image_tag(sha: str, ref_name: str, *, max_length: int = MAX_TAG_LENGTH) -> str:
    """Return sha-<commit>-<branch>, trimmed to the registry limit."""
    if not sha or any(char not in _HEX for char in sha):
        raise ValueError("sha must be hex")
    branch = sanitize_branch(ref_name)
    if not branch:
        raise ValueError("branch name is empty after sanitising")
    prefix = f"sha-{sha}-"
    room = max_length - len(prefix)
    if room < 1:
        raise ValueError("sha prefix exceeds max tag length")
    return prefix + branch[:room]


def push_latest(ref_name: str) -> bool:
    """Only main may move the latest tag."""
    return ref_name == "main"


def _write_output(name: str, value: str) -> None:
    line = f"{name}={value}\n"
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(line)


def main() -> int:
    sha = os.environ["GITHUB_SHA"]
    ref_name = os.environ.get("GITHUB_REF_NAME", "")
    tag = build_image_tag(sha, ref_name)
    latest = "true" if push_latest(ref_name) else "false"
    _write_output("tag", tag)
    _write_output("push_latest", latest)
    print(tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
