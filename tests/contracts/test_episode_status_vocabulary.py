"""VT-LEO-AI-527: EpisodeOfCare status vocabulary contract.

Pins the canonical status vocabulary defined in
``libs/episodes/status.py`` so:

  * the Haiku Episode Engine writer cannot regress to an invalid value
    (the historical ``benign_closed`` -> ``closed_benign`` defect),
  * production code outside the canonical module cannot reintroduce a
    raw status string literal (the dashboard / writer drift that caused
    benign closures to appear as 'active'),
  * the TypeScript mirror at ``services/ui/src/lib/episodeStatus.ts``
    stays in lockstep with the Python source of truth.

These tests parse files as text -- they do not import the UI bundle -- so
they run inside the standard pytest suite with no Node toolchain.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from libs.episodes.status import (
    ALWAYS_EXCLUDE_STATUSES,
    CLOSED_STATUSES,
    CLOSURE_REASON_STATUSES,
    ENGINE_OUTPUT_STATUSES,
    LEGACY_STATUS_REWRITES,
    OPEN_STATUSES,
    EpisodeStatus,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TS_MIRROR = (
    REPO_ROOT / "services" / "ui" / "src" / "lib" / "episodeStatus.ts"
)


# ---------------------------------------------------------------------------
# 1. Producer contract: the writer maps every reconciled episode shape to a
#    canonical engine-output status.
# ---------------------------------------------------------------------------


def test_writer_only_emits_engine_output_statuses():
    """VT-527-TC-001: the writer's ``_episode_status`` returns one of the
    four canonical engine-output statuses for the four code paths."""
    from services.analysis_worker.app.episode_engine.writer import (
        _episode_status,
    )
    from services.analysis_worker.app.episode_engine.schemas import (
        Milestone,
        ReconciledEpisode,
    )
    from datetime import date

    def _ep(**kw) -> ReconciledEpisode:
        defaults = dict(
            episode_id="ep-test",
            suspected_site="lung",
            episode_type="cancer",
            window_start=date(2025, 1, 1),
            window_end=None,
            milestones=[],
            confidence=0.9,
            reasoning="x",
            needs_human_review=False,
            merged_from=[],
        )
        defaults.update(kw)
        return ReconciledEpisode(**defaults)

    benign = _ep(episode_type="benign")
    completed = _ep(
        milestones=[
            Milestone(
                type="treatment_completed",
                date=date(2025, 6, 1),
                encounter_id="enc-1",
                evidence_quote="treatment completed today",
                confidence=0.9,
                reasoning="reason",
            )
        ]
    )
    review = _ep(needs_human_review=True)
    active = _ep()

    actual = {
        _episode_status(benign),
        _episode_status(completed),
        _episode_status(review),
        _episode_status(active),
    }
    assert actual <= ENGINE_OUTPUT_STATUSES, (
        f"Writer emitted statuses outside ENGINE_OUTPUT_STATUSES: "
        f"{actual - ENGINE_OUTPUT_STATUSES}"
    )
    # The four code paths must all produce distinct values.
    assert len(actual) == 4


def test_engine_output_statuses_are_a_subset_of_legal_vocabulary():
    """VT-527-TC-002: every engine-output status is a member of the
    canonical EpisodeStatus enum."""
    legal = {s.value for s in EpisodeStatus}
    assert ENGINE_OUTPUT_STATUSES <= legal


def test_canonical_benign_status_is_closed_benign_not_benign_closed():
    """VT-527-TC-003: the benign-closure status is spelled
    ``closed_benign`` (matches DI-085, dashboard ``_CLOSED`` set, UI
    EPISODE_STATUS_LABELS, EpisodeTimeline CLOSURE_STATUSES). The
    inverted spelling ``benign_closed`` must NOT exist anywhere except
    in the legacy-rewrite map."""
    assert EpisodeStatus.CLOSED_BENIGN.value == "closed_benign"
    assert "benign_closed" in LEGACY_STATUS_REWRITES
    assert LEGACY_STATUS_REWRITES["benign_closed"] == "closed_benign"
    assert "benign_closed" not in {s.value for s in EpisodeStatus}


# ---------------------------------------------------------------------------
# 2. Consumer contract: dashboard's CLOSED set + mission-control's
#    closure-reason / always-exclude lists are imported from the canonical
#    module, not re-declared.
# ---------------------------------------------------------------------------


def test_dashboard_closed_set_matches_canonical():
    """VT-527-TC-004: the audit dashboard's ``_CLOSED`` set IS the
    canonical CLOSED_STATUSES (imported, not re-declared)."""
    from services.analytics_api.app.routers import audit

    src = Path(audit.__file__).read_text(encoding="utf-8")
    assert "from libs.episodes.status import" in src
    assert "CLOSED_STATUSES" in src
    # The inline literal block must NOT be present any more.
    assert "_CLOSED = {" not in src or "_CLOSED = CLOSED_STATUSES" in src


def test_mission_control_uses_canonical_closure_constants():
    """VT-527-TC-005: mission-control re-exports ``_CLOSURE_STATUSES`` /
    ``_ALWAYS_EXCLUDE`` from the canonical module."""
    from services.analytics_api.app.routers import mission_control

    src = Path(mission_control.__file__).read_text(encoding="utf-8")
    assert "from libs.episodes.status import" in src
    assert (
        mission_control._CLOSURE_STATUSES == list(CLOSURE_REASON_STATUSES)
    )
    assert (
        mission_control._ALWAYS_EXCLUDE == list(ALWAYS_EXCLUDE_STATUSES)
    )


# ---------------------------------------------------------------------------
# 3. TypeScript mirror parity. The contract test parses the TS file as
#    text and asserts the exported sets match the Python sets.
# ---------------------------------------------------------------------------


def _ts_string_constants(src: str) -> dict[str, str]:
    """Parse ``export const STATUS_FOO = "foo";`` declarations."""
    out = {}
    for m in re.finditer(
        r'export\s+const\s+(STATUS_[A-Z_]+)\s*=\s*"([^"]+)"\s*;', src
    ):
        out[m.group(1)] = m.group(2)
    return out


def _ts_literal_set(src: str, set_name: str) -> set[str]:
    """Parse ``export const SOME_SET ... = new Set([STATUS_FOO, ...]);``
    or ``... = new Set([\"foo\", ...]);``."""
    pat = re.compile(
        r"export\s+const\s+"
        + re.escape(set_name)
        + r"[^=]*=\s*new\s+Set\(\s*\[(.*?)\]\s*\)\s*;",
        re.DOTALL,
    )
    m = pat.search(src)
    assert m is not None, f"Could not find {set_name} in TS mirror"
    return _resolve_items(m.group(1), src)


def _ts_literal_array(src: str, name: str) -> list[str]:
    """Parse ``export const NAME ... = [STATUS_FOO, ...];``."""
    pat = re.compile(
        r"export\s+const\s+"
        + re.escape(name)
        + r"[^=]*=\s*\[(.*?)\]\s*;",
        re.DOTALL,
    )
    m = pat.search(src)
    assert m is not None, f"Could not find {name} in TS mirror"
    return list(_resolve_items_ordered(m.group(1), src))


def _resolve_items(raw: str, full_src: str) -> set[str]:
    return set(_resolve_items_ordered(raw, full_src))


def _resolve_items_ordered(raw: str, full_src: str) -> list[str]:
    constants = _ts_string_constants(full_src)
    items: list[str] = []
    for tok in raw.split(","):
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


@pytest.fixture(scope="module")
def ts_src() -> str:
    return TS_MIRROR.read_text(encoding="utf-8")


def test_ts_mirror_exists(ts_src: str):
    """VT-527-TC-006: the TS mirror file is present at the canonical
    path so every UI consumer has a single import target."""
    assert "Canonical EpisodeOfCare status vocabulary" in ts_src
    assert "MIRROR of libs/episodes/status.py" in ts_src


def test_ts_mirror_engine_output_statuses_match(ts_src: str):
    """VT-527-TC-007: ENGINE_OUTPUT_STATUSES TS set equals Python set."""
    ts_set = _ts_literal_set(ts_src, "ENGINE_OUTPUT_STATUSES")
    assert ts_set == set(ENGINE_OUTPUT_STATUSES)


def test_ts_mirror_open_statuses_match(ts_src: str):
    """VT-527-TC-008: OPEN_STATUSES TS set equals Python set."""
    ts_set = _ts_literal_set(ts_src, "OPEN_STATUSES")
    assert ts_set == set(OPEN_STATUSES)


def test_ts_mirror_closed_statuses_match(ts_src: str):
    """VT-527-TC-009: CLOSED_STATUSES TS set equals Python set."""
    ts_set = _ts_literal_set(ts_src, "CLOSED_STATUSES")
    assert ts_set == set(CLOSED_STATUSES)


def test_ts_mirror_closure_reason_order_match(ts_src: str):
    """VT-527-TC-010: CLOSURE_REASON_STATUSES order matches (the UI
    shows the chips in this order)."""
    ts_arr = _ts_literal_array(ts_src, "CLOSURE_REASON_STATUSES")
    assert tuple(ts_arr) == CLOSURE_REASON_STATUSES


def test_ts_mirror_always_exclude_match(ts_src: str):
    """VT-527-TC-011: ALWAYS_EXCLUDE_STATUSES order matches."""
    ts_arr = _ts_literal_array(ts_src, "ALWAYS_EXCLUDE_STATUSES")
    assert tuple(ts_arr) == ALWAYS_EXCLUDE_STATUSES


def test_ts_mirror_legacy_rewrites_match(ts_src: str):
    """VT-527-TC-012: legacy rewrite map matches between Py and TS."""
    pat = re.compile(
        r"LEGACY_STATUS_REWRITES[^=]*=\s*\{(.*?)\}\s*;", re.DOTALL
    )
    m = pat.search(ts_src)
    assert m is not None, "LEGACY_STATUS_REWRITES not found in TS mirror"
    body = m.group(1)
    constants = _ts_string_constants(ts_src)
    found = {}
    for entry in re.finditer(
        r'(\w+)\s*:\s*(STATUS_[A-Z_]+|"[^"]+")', body
    ):
        key, val = entry.group(1), entry.group(2)
        if val.startswith('"'):
            found[key] = val[1:-1]
        else:
            found[key] = constants[val]
    assert found == LEGACY_STATUS_REWRITES


# ---------------------------------------------------------------------------
# 4. No raw literal regressions. Greps the production tree for the
#    forbidden ``benign_closed`` token and any other status string used
#    outside an approved location. Keeps the dashboard / writer / UI
#    from drifting again.
# ---------------------------------------------------------------------------


# Files allowed to mention the forbidden legacy spelling because they
# document the migration itself.
_BENIGN_CLOSED_ALLOWLIST = {
    "libs/episodes/status.py",
    "services/ui/src/lib/episodeStatus.ts",
    "scripts/migrations/2026_normalise_episode_status_vocabulary.py",
    "scripts/migrations/2026_unify_episode_lifecycle.py",
    "tests/contracts/test_episode_status_vocabulary.py",
}


def _walk_production_files() -> list[Path]:
    roots = ["services", "libs", "scripts"]
    out: list[Path] = []
    for root in roots:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix not in {".py", ".ts", ".tsx"}:
                continue
            # Skip generated, vendor, build, and one-off investigation
            # scripts (those are deliberately exempt -- they read the
            # historical graph state, not a target for production lint).
            parts = set(p.parts)
            if parts & {
                "node_modules",
                ".next",
                "__pycache__",
                "investigations",
                "spike",
            }:
                continue
            out.append(p)
    return out


def test_no_production_file_uses_benign_closed_literal():
    """VT-527-TC-013: the forbidden legacy spelling ``benign_closed``
    appears only in the canonical module, the migration script, this
    contract test, and the TS mirror -- nowhere in production code."""
    offenders: list[str] = []
    for path in _walk_production_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in _BENIGN_CLOSED_ALLOWLIST:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "benign_closed" in text:
            offenders.append(rel)
    assert not offenders, (
        "These files use the forbidden legacy status spelling "
        "'benign_closed' (use closed_benign via libs/episodes/status.py): "
        + ", ".join(sorted(offenders))
    )


# ---------------------------------------------------------------------------
# 5. Writer parity (DI-C4CEFA32). Every backend writer of
#    EpisodeOfCare.status MUST emit a member of
#    libs.episodes.status.EpisodeStatus -- not the legacy 'in_review',
#    not the v2 boundary labels 'open' / 'closed' / 'benign_closure',
#    not anything else. This guards against a regression where a
#    writer is added that bypasses the canonical lifecycle module.
# ---------------------------------------------------------------------------


# Files allowed to mention the forbidden non-canonical status string
# literals because they are migrations / lifecycle helpers / tests
# that document the migration itself.
_NON_CANONICAL_STATUS_ALLOWLIST = {
    "libs/episodes/status.py",
    "libs/episodes/lifecycle.py",
    "services/ui/src/lib/episodeStatus.ts",
    "scripts/migrations/2026_normalise_episode_status_vocabulary.py",
    "scripts/migrations/2026_unify_episode_lifecycle.py",
    "tests/contracts/test_episode_status_vocabulary.py",
    "tests/episodes/test_lifecycle.py",
    "tests/episode_detector_v2/test_runner_persist_canonical.py",
    # Boundary detector and tests own the internal 'open'/'closed'/
    # 'benign_closure' vocabulary; the canonical translator
    # (canonical_status_from_v2_boundary) projects it to canonical
    # before any persist happens.
    "services/analysis_worker/app/episode_detector_v2/boundary.py",
}


# Forbidden non-canonical status STRING LITERALS that production
# writers must not emit. These are the spellings shipped to the live
# graph before DI-C4CEFA32 unified the lifecycle.
_FORBIDDEN_STATUS_LITERALS: tuple[str, ...] = (
    "in_review",
    # Note: 'open', 'closed', 'benign_closure' appear elsewhere
    # (e.g. as field names, dictionary keys, or non-status string
    # values like "open episodes"). We only flag them when they
    # appear in a context that matches a Cypher SET on a status
    # column or a Python writer assigning ep.status. The simpler
    # 'in_review' spelling is unambiguous and is the highest-value
    # gate for this contract.
)


# Patterns that suggest an EpisodeOfCare.status WRITE in TS or
# Python, where the value 'in_review' would land on the graph
# instead of the canonical 'review'. We deliberately do NOT flag:
#   * comments ("// in_review default"),
#   * HeroBucket labels (`in_review` is a UI bucket name, separate
#     vocabulary owned by libs/episodes/lifecycle.py),
#   * response-field keys like `in_review_episodes`,
#   * legacy-rewrite map keys (those legitimately mention the
#     legacy spelling, by definition).
_WRITER_LITERAL_PATTERNS_IN_REVIEW: tuple[re.Pattern[str], ...] = (
    # TS object literal: status: "in_review"
    re.compile(r'\bstatus\s*:\s*["\']in_review["\']'),
    # TS arrow / assignment: status = "in_review"
    re.compile(r'\bstatus\s*=\s*["\']in_review["\']'),
    # Python kwarg / dict: status="in_review" or 'status': 'in_review'
    re.compile(r'\bstatus\s*=\s*["\']in_review["\']'),
    re.compile(r'["\']status["\']\s*:\s*["\']in_review["\']'),
    # Cypher SET clause embedded in a Python f-string / triple-string.
    re.compile(r'\.status\s*=\s*["\']in_review["\']'),
)


def _strip_line_comment(line: str) -> str:
    """Remove a trailing line-comment so the writer scan does not
    flag literals that only appear inside ``// ...`` / ``# ...`` /
    `` * ...`` (JSDoc) commentary."""
    stripped = line.lstrip()
    if stripped.startswith(("//", "#", "*")):
        return ""
    # Strip trailing // ... or # ... preserving string-literal content
    # that contains those tokens (close enough for this lint -- the
    # writer patterns we care about would not embed `// ` or `# ` in
    # the same statement).
    for marker in ("//", "#"):
        idx = line.find(f" {marker}")
        if idx >= 0:
            line = line[:idx]
    return line


def test_no_production_writer_uses_legacy_in_review_literal():
    """VT-66DA36EC-TC-001: no production writer assigns the legacy
    ``in_review`` status string to ``EpisodeOfCare.status``. Use
    ``EpisodeStatus.REVIEW.value`` (= ``"review"``) instead.

    Comments, hero-bucket labels (``in_review`` as a UI bucket name),
    legacy-rewrite map keys, and response-field keys
    (``in_review_episodes``) are deliberately NOT flagged -- only
    direct assignments to a ``status`` field in non-comment lines of
    production (non-test) source files."""
    offenders: list[str] = []
    for path in _walk_production_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in _NON_CANONICAL_STATUS_ALLOWLIST:
            continue
        # Skip test files: tests intentionally seed legacy status
        # values to verify backward compatibility / migration paths.
        if (
            "__tests__" in rel
            or "/tests/" in rel
            or rel.endswith(".test.ts")
            or rel.endswith(".test.tsx")
            or rel.endswith(".test.py")
            or "/test_" in rel
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_no, raw_line in enumerate(text.splitlines(), start=1):
            line = _strip_line_comment(raw_line)
            if not line:
                continue
            for pat in _WRITER_LITERAL_PATTERNS_IN_REVIEW:
                if pat.search(line):
                    offenders.append(f"{rel}:{line_no} {line.strip()}")
                    break
    assert not offenders, (
        "These production writers assign the legacy 'in_review' "
        "status to EpisodeOfCare.status. Switch to "
        "EpisodeStatus.REVIEW.value (Python) or STATUS_REVIEW (TS):\n"
        + "\n".join(sorted(offenders))
    )
