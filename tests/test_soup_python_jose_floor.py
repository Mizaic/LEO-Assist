"""Regression guard for the python-jose SOUP anomaly (DI-A30F58D6 / DO-FA6A62FC).

python-jose[cryptography] performs JWT/JWK verification at the OAuth
callback auth boundary (services/api/app/routers/auth.py). Versions below
3.4.0 are affected by CVE-2024-33663 (algorithm confusion) and
CVE-2024-33664 (JWE denial-of-service). This test asserts the version
floor in every production Dockerfile's requirements.txt so a future edit
cannot silently reintroduce the vulnerable range.

See compliance/policy/DC-SOUP-001-soup-list.md, Section 3.2 item 1 / 7.4.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

MINIMUM_SAFE_VERSION = (3, 4, 0)

# Every service whose Dockerfile installs directly from its own
# requirements.txt and imports python-jose for token verification.
REQUIREMENTS_FILES = [
    "requirements.txt",
    "services/api/requirements.txt",
    "services/fhir_api/requirements.txt",
    "services/pipeline_worker/requirements.txt",
]

FLOOR_PATTERN = re.compile(
    r"^python-jose\[cryptography\]\s*>=\s*(\d+)\.(\d+)\.(\d+)\s*$",
    re.MULTILINE,
)


def _find_floor(requirements_text: str) -> tuple[int, int, int]:
    match = FLOOR_PATTERN.search(requirements_text)
    assert match is not None, (
        "python-jose[cryptography]>=X.Y.Z not found (or floor is not "
        "fully qualified, e.g. '>=3.3' instead of '>=3.4.0')"
    )
    return tuple(int(part) for part in match.groups())


@pytest.mark.parametrize("relative_path", REQUIREMENTS_FILES)
def test_python_jose_floor_excludes_known_cves(relative_path: str) -> None:
    requirements_path = REPO_ROOT / relative_path
    assert requirements_path.exists(), f"missing {relative_path}"

    floor = _find_floor(requirements_path.read_text())

    assert floor >= MINIMUM_SAFE_VERSION, (
        f"{relative_path} floors python-jose at {'.'.join(map(str, floor))}, "
        f"below {'.'.join(map(str, MINIMUM_SAFE_VERSION))}. This permits "
        "builds affected by CVE-2024-33663 / CVE-2024-33664."
    )
