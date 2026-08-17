"""Run the gated LEO phone-home digest against the Atlas NCR facade.

Atlas: DI-C7DEF132

Usage:
  python scripts/phone_home_digest.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from libs.atlas_qms.phone_home import digest_phone_home


def main() -> int:
    print(json.dumps(digest_phone_home(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
