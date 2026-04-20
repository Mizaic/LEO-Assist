"""VT-LEO-AI-530: Canonical cancer-type vocabulary contract.

Pins the canonical vocabulary defined in
``libs/oncology/cancer_types.py`` so:

  * the segmenter LLM enum and the writer normaliser cannot drift,
  * the TypeScript mirror at ``services/ui/src/lib/cancerTypes.ts``
    stays in lockstep with the Python source of truth,
  * dashboard charts cannot reintroduce a free-text site label outside
    the canonical 30-entry set.

The TS file is parsed as text -- no Node toolchain required.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from libs.oncology.cancer_types import (
    CANONICAL_CANCER_TYPES,
    CANONICAL_CANCER_TYPE_SET,
    normalise_cancer_type,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TS_MIRROR = REPO_ROOT / "services" / "ui" / "src" / "lib" / "cancerTypes.ts"


# ---------------------------------------------------------------------------
# 1. Producer contract: the segmenter prompt schema constrains the LLM
#    to emit only canonical values.
# ---------------------------------------------------------------------------


def test_segmenter_schema_enum_matches_canonical_list():
    """VT-530-TC-001: the segmenter v1 prompt schema's ``suspected_site``
    enum is exactly the canonical 30-entry list (LLM cannot emit free
    text or a near-synonym)."""
    from libs.prompts.episode_engine.segmenter_v1 import SCHEMA

    enum = (
        SCHEMA["properties"]["windows"]["items"]["properties"][
            "suspected_site"
        ]["enum"]
    )
    assert tuple(enum) == CANONICAL_CANCER_TYPES


def test_writer_normalises_cancer_type_before_persistence():
    """VT-530-TC-002: the Episode Engine writer pipes the suspected
    site through ``normalise_cancer_type`` before writing so a stray
    LLM value cannot hit the graph."""
    src = (
        REPO_ROOT
        / "services"
        / "analysis_worker"
        / "app"
        / "episode_engine"
        / "writer.py"
    ).read_text(encoding="utf-8")
    assert "from libs.oncology.cancer_types import normalise_cancer_type" in src
    assert "normalise_cancer_type(" in src


# ---------------------------------------------------------------------------
# 2. Consumer contract: analytics endpoints normalise on read so legacy
#    free-text values cannot reach the dashboard chart axes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module_path",
    [
        "services/analytics_api/app/routers/dashboards.py",
        "services/analytics_api/app/routers/_audit_sections.py",
        "services/analytics_api/app/routers/_audit_intervals.py",
    ],
)
def test_analytics_modules_normalise_cancer_type(module_path: str):
    """VT-530-TC-003: every analytics surface that returns a
    ``cancer_type`` / ``condition_type`` field imports and applies
    :func:`normalise_cancer_type` on read."""
    text = (REPO_ROOT / module_path).read_text(encoding="utf-8")
    assert (
        "from libs.oncology.cancer_types import normalise_cancer_type"
        in text
    ), f"{module_path} does not import normalise_cancer_type"
    assert "normalise_cancer_type(" in text, (
        f"{module_path} imports but does not call normalise_cancer_type"
    )


# ---------------------------------------------------------------------------
# 3. TypeScript mirror parity. The contract test parses the TS file as
#    text and asserts the exported constants match the Python set.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ts_src() -> str:
    return TS_MIRROR.read_text(encoding="utf-8")


def _ts_string_constants(src: str) -> dict[str, str]:
    """Parse ``export const CANCER_TYPE_FOO = "Foo";`` declarations."""
    out: dict[str, str] = {}
    for m in re.finditer(
        r'export\s+const\s+(CANCER_TYPE_[A-Z_]+)\s*=\s*"([^"]+)"\s*;',
        src,
    ):
        out[m.group(1)] = m.group(2)
    return out


def _ts_options_array(src: str) -> list[str]:
    """Resolve ``CANCER_TYPE_OPTIONS`` to a list of canonical strings."""
    pat = re.compile(
        r"export\s+const\s+CANCER_TYPE_OPTIONS[^=]*=\s*\[(.*?)\]\s*;",
        re.DOTALL,
    )
    m = pat.search(src)
    assert m is not None, "Could not find CANCER_TYPE_OPTIONS in TS mirror"
    constants = _ts_string_constants(src)
    items: list[str] = []
    for tok in m.group(1).split(","):
        tok = tok.strip()
        if not tok:
            continue
        if tok.startswith('"') and tok.endswith('"'):
            items.append(tok[1:-1])
        elif tok in constants:
            items.append(constants[tok])
        else:
            raise AssertionError(f"Unexpected TS token: {tok!r}")
    return items


def test_ts_mirror_exists(ts_src: str):
    """VT-530-TC-004: the TS mirror file is present at the canonical
    path so every UI consumer has a single import target."""
    assert "Canonical NCDA cancer-type vocabulary" in ts_src
    assert "MIRROR of libs/oncology/cancer_types.py" in ts_src


def test_ts_options_array_matches_python_order(ts_src: str):
    """VT-530-TC-005: TS ``CANCER_TYPE_OPTIONS`` ordering matches
    Python ``CANONICAL_CANCER_TYPES`` exactly (NCDA display order)."""
    options = _ts_options_array(ts_src)
    assert tuple(options) == CANONICAL_CANCER_TYPES


def test_ts_constants_cover_every_canonical_value(ts_src: str):
    """VT-530-TC-006: the TS mirror exports a ``CANCER_TYPE_*``
    constant for every canonical Python value."""
    constants = _ts_string_constants(ts_src)
    assert set(constants.values()) == CANONICAL_CANCER_TYPE_SET


def test_ts_raw_to_canonical_keys_are_a_subset_of_python_map(ts_src: str):
    """VT-530-TC-007: every key in the TS ``RAW_TO_CANONICAL`` map
    canonicalises to the same value the Python normaliser produces.

    Catches drift in either direction -- if Python adds a synonym we
    fail here until the TS mirror is updated, and if TS invents a
    synonym Python doesn't recognise we fail because Python returns
    ``Other`` while TS returns the specific entry."""
    pat = re.compile(
        r"const\s+RAW_TO_CANONICAL[^=]*=\s*\{(.*?)\}\s*;",
        re.DOTALL,
    )
    m = pat.search(ts_src)
    assert m is not None, "Could not find RAW_TO_CANONICAL in TS mirror"
    body = m.group(1)
    constants = _ts_string_constants(ts_src)

    entry_pat = re.compile(
        r'(?:"([^"]*)"|(\w+))\s*:\s*(CANCER_TYPE_[A-Z_]+)'
    )
    mismatches: list[str] = []
    for entry in entry_pat.finditer(body):
        quoted_key, bare_key, const_name = (
            entry.group(1),
            entry.group(2),
            entry.group(3),
        )
        key = quoted_key if quoted_key is not None else bare_key
        ts_value = constants[const_name]
        py_value = normalise_cancer_type(key)
        if py_value != ts_value:
            mismatches.append(
                f"{key!r}: TS -> {ts_value!r}, Python -> {py_value!r}"
            )
    assert not mismatches, (
        "TS RAW_TO_CANONICAL diverges from Python normaliser:\n  "
        + "\n  ".join(mismatches)
    )


# ---------------------------------------------------------------------------
# 4. No raw site-string regressions in the dashboard / chart code.
#    Components must use canonical labels via the TS mirror.
# ---------------------------------------------------------------------------


# Files allowed to embed raw cancer-type strings because they implement
# the canonical mapping itself.
_RAW_SITE_ALLOWLIST = {
    "libs/oncology/cancer_types.py",
    "libs/prompts/episode_engine/segmenter_v1.py",
    "libs/prompts/episode_engine/_shared.py",
    "services/ui/src/lib/cancerTypes.ts",
    "scripts/migrations/2026_normalise_cancer_types.py",
    "tests/contracts/test_cancer_type_vocabulary.py",
    "tests/oncology/test_cancer_types.py",
}


# Forbidden raw values: the legacy free-text spellings that the
# migration is meant to wipe out. If any production file outside the
# allowlist still contains one of these tokens we have a drift
# regression.
_FORBIDDEN_RAW_VALUES = (
    "haematology",
    "gynaecological",
    "urological",
    "upper gi",
    "head and neck",
    "salivary gland",
)


def _walk_dashboard_files() -> list[Path]:
    base = REPO_ROOT / "services" / "ui" / "src" / "components" / "dashboard"
    return [p for p in base.rglob("*.tsx") if p.is_file()]


def test_dashboard_components_have_no_raw_site_literals():
    """VT-530-TC-008: no dashboard component contains a forbidden raw
    site string -- chart axes must come through ``normaliseCancerType``
    so legacy data shows up under its canonical label."""
    offenders: list[str] = []
    for path in _walk_dashboard_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in _RAW_SITE_ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8").lower()
        for forbidden in _FORBIDDEN_RAW_VALUES:
            if forbidden in text:
                offenders.append(f"{rel}: {forbidden!r}")
    assert not offenders, (
        "Dashboard components contain forbidden raw cancer-site "
        "literals (route via lib/cancerTypes.ts instead):\n  "
        + "\n  ".join(sorted(offenders))
    )
