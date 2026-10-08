#!/usr/bin/env python3
"""Write dist/built-services.json for the CD selective-deploy step.

Atlas trace:
  DO: DO-6036D724
  DI: DI-71087A9E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-6036D724")
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_CI_DIR = str(Path(__file__).resolve().parent)
if _CI_DIR not in sys.path:
    sys.path.insert(0, _CI_DIR)
from image_tag import build_image_tag  # noqa: E402


def _image_tag(sha: str) -> str:
    explicit = os.environ.get("IMAGE_TAG", "").strip()
    if explicit:
        return explicit
    return build_image_tag(sha, os.environ.get("GITHUB_REF_NAME", ""))


def main() -> int:
    services = [s for s in os.environ.get("SERVICES_CSV", "").split(",") if s]
    sha = os.environ["GITHUB_SHA"]
    manifest = {
        "sha": sha,
        "image_tag": _image_tag(sha),
        "build_all": os.environ.get("BUILD_ALL") == "true",
        "services": services,
    }
    out = Path("dist/built-services.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
