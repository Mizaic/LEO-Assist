"""Safety-netting signal detection for NCDA cancer episodes.

NCDA Section 8 ("Safety netting") asks the auditor to record whether the
GP documented a safety-netting plan during the workup of a confirmed
cancer (e.g. "if you develop new bleeding, return immediately"; or the
PRISM template field "Advice if worsens, no better or concerns: Yes";
or the dedicated EMIS Read code Y281b "Cancer safety netting").

The episode writer (``scripts/ncda/run_full_cancer_episode_detection.py``)
calls :func:`detect_safety_netting` after each episode is MERGEd, passing
every encounter text in the milestone-anchored window
``[earliest_milestone - 30d, latest_milestone + 14d]``. The result is
persisted onto the EpisodeOfCare node so the audit dashboard can surface
the rate without re-scanning the encounter text on every page-load.

Three signal strengths are reported (mutually exclusive — the strongest
match wins):

  - ``"strong"``       structured EMIS Read code ``Y281b`` is present
                        (or its rendered phrase "Cancer safety netting"),
                        OR an explicit "safety net" / "safety netting" /
                        "safety advice" free-text phrase appears in the
                        plan section. This is what the NCDA reviewer
                        would tick "Yes" against.

  - ``"medium"``       a PRISM 2WW questionnaire field
                        ``Advice if worsens, no better or concerns: Yes``
                        is present. The structured form was completed
                        but the GP did not write a free-text plan —
                        defensible but weaker than ``strong``.

  - ``"advice_only"``  generic "return if X", "come back if X",
                        "reattend if X", "if symptoms persist", "red
                        flag" phrasing in the plan section. This is the
                        most permissive bucket and should NOT be the
                        denominator for the headline NCDA statistic
                        (the same phrasing is used routinely on minor
                        ailments, so it is a noisy signal in isolation).

  - ``"none"``         no safety-netting evidence found in the window.

Exposing all four buckets lets the dashboard render the most defensible
number (``strong + medium``) by default while still showing the
permissive number behind a tooltip — consistent with the rest of the
NCDA report (Section 8 is graded "Yes / Partially / No").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Literal

# ---------------------------------------------------------------------------
# Signal patterns
# ---------------------------------------------------------------------------

#: Strong signal #1 — structured EMIS Read code (and its template render).
_STRONG_CODE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bY281b\b", re.IGNORECASE),
    re.compile(r"cancer\s+safety[\s\-]?netting", re.IGNORECASE),
)

#: Strong signal #2 — explicit free-text phrase in the plan section.
#: ``safety[\s\-]?net(?:ting|ted)?`` matches "safety net", "safety-net",
#: "safety netting", "safety netted", "safetynet", "safetynetting" and
#: "safetynetted" (a single regex covers the lot).
_STRONG_PHRASE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"safety[\s\-]?net(?:ting|ted)?", re.IGNORECASE),
    re.compile(r"safety[\s\-]?advice", re.IGNORECASE),
)

#: Medium signal — PRISM 2WW questionnaire structured field.
#: The PRISM templates render this as
#: ``Advice if worsens, no better or concerns: Yes``.
_MEDIUM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"advice\s+if\s+worsens[^\n]{0,80}:\s*yes",
        re.IGNORECASE,
    ),
)

#: Advice-only signal — generic "return if X" phrasing seen on routine
#: appointments. Useful for the permissive denominator only.
_ADVICE_ONLY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\breturn\s+if\b", re.IGNORECASE),
    re.compile(r"\bcome\s+back\s+if\b", re.IGNORECASE),
    re.compile(r"\breattend\s+if\b", re.IGNORECASE),
    re.compile(r"\bif\s+symptoms\s+(?:persist|worsen|continue)\b", re.IGNORECASE),
    re.compile(r"\bif\s+no\s+improvement\b", re.IGNORECASE),
    re.compile(r"\bred[\s\-]?flag(?:s|ged)?\b", re.IGNORECASE),
)

#: Noise filter — phrases that contain "safety net" but refer to a
#: third-party CBS/QOF protocol echo, not a clinician-recorded safety
#: net for the index pathway (e.g. "Cancer safety netting (CBS claim):
#: Yes" appears on every PSA-monitoring patient regardless of whether
#: the GP discussed it). When the only "strong" hits in the encounter
#: text are surrounded by claim/QOF markers, downgrade to "medium".
_CLAIM_ECHO_PATTERN = re.compile(
    r"(?:cbs\s+claim|cbs\s+register|qof|register\s+code|claim\s+code)"
    r"[^\n]{0,40}safety[\s\-]?net|"
    r"safety[\s\-]?net[^\n]{0,40}(?:cbs\s+claim|cbs\s+register|qof|"
    r"register\s+code|claim\s+code)",
    re.IGNORECASE,
)


SafetyNettingSignal = Literal["strong", "medium", "advice_only", "none"]


@dataclass(frozen=True)
class SafetyNettingMatch:
    """Result of scanning one episode's window for safety-netting evidence.

    Attributes:
        recorded:        Convenience boolean — True when ``signal`` is
                         ``"strong"`` or ``"medium"``. This is the value
                         the NCDA reviewer would tick "Yes" against and
                         the field the dashboard tile reads.
        signal:          Strongest signal found, in the hierarchy
                         strong > medium > advice_only > none.
        code_hits:       Distinct EMIS Read codes / structured-template
                         phrases found (e.g. ``["Y281b"]``).
        phrase_hits:     Distinct free-text phrases found (lowercased,
                         deduplicated, sorted for stable output).
        evidence_count:  Total number of encounter texts that produced
                         at least one hit. Useful for the dashboard
                         tooltip ("recorded across N visits").
    """

    recorded: bool
    signal: SafetyNettingSignal
    code_hits: tuple[str, ...] = field(default_factory=tuple)
    phrase_hits: tuple[str, ...] = field(default_factory=tuple)
    evidence_count: int = 0


def _scan_one(text: str) -> tuple[SafetyNettingSignal, list[str], list[str]]:
    """Classify a single encounter text. Returns (signal, codes, phrases)."""
    if not text:
        return "none", [], []

    code_hits: list[str] = []
    for pat in _STRONG_CODE_PATTERNS:
        for m in pat.finditer(text):
            code_hits.append(m.group(0).strip())

    phrase_hits: list[str] = []
    for pat in _STRONG_PHRASE_PATTERNS:
        for m in pat.finditer(text):
            phrase_hits.append(m.group(0).strip().lower())

    has_strong_code = bool(code_hits)
    has_strong_phrase = bool(phrase_hits)

    has_medium = any(p.search(text) for p in _MEDIUM_PATTERNS)
    has_advice = any(p.search(text) for p in _ADVICE_ONLY_PATTERNS)

    # Down-weight QOF/CBS-claim echoes: if the only strong hits in this
    # encounter are inside a claim-code template line and the clinician
    # did not write a free-text safety-net note in the plan section,
    # the encounter still counts as medium evidence (the patient is
    # documented on a structured safety-netting protocol) but not
    # strong (no clinician-recorded plan in the index visit).
    if has_strong_code or has_strong_phrase:
        is_only_claim_echo = (
            _CLAIM_ECHO_PATTERN.search(text) is not None
            and not _has_clinician_safety_net(text)
        )
        if is_only_claim_echo:
            return "medium", [], []
        return "strong", code_hits, phrase_hits

    if has_medium:
        return "medium", [], []
    if has_advice:
        return "advice_only", [], []
    return "none", [], []


def _has_clinician_safety_net(text: str) -> bool:
    """Return True if the text contains a safety-net phrase OUTSIDE the
    QOF/CBS-claim template echo (i.e. a clinician actually wrote it in
    the plan section rather than the structured report header)."""
    # Strip any "(...CBS claim...): Yes" template lines and re-scan.
    stripped = re.sub(
        r"[^\n]*(?:cbs\s+claim|cbs\s+register|qof|register\s+code|"
        r"claim\s+code)[^\n]*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return any(p.search(stripped) for p in _STRONG_PHRASE_PATTERNS) or any(
        p.search(stripped) for p in _STRONG_CODE_PATTERNS
    )


def detect_safety_netting(texts: Iterable[str]) -> SafetyNettingMatch:
    """Scan a collection of encounter texts for safety-netting evidence.

    Pass every encounter text in the episode's milestone-anchored window
    (``[earliest_milestone - 30d, latest_milestone + 14d]``) so the
    detector picks up safety-net advice given at the GP visit that
    triggered the referral as well as any post-referral chase-up.

    The return value is the strongest signal across all texts. Per-text
    counts are aggregated into ``evidence_count`` (number of encounters
    that produced at least one hit) so the dashboard tooltip can render
    "recorded at N of M visits".
    """
    signal_rank: dict[SafetyNettingSignal, int] = {
        "none": 0,
        "advice_only": 1,
        "medium": 2,
        "strong": 3,
    }
    best: SafetyNettingSignal = "none"
    all_codes: set[str] = set()
    all_phrases: set[str] = set()
    evidence_count = 0

    for text in texts:
        sig, codes, phrases = _scan_one(text or "")
        if sig != "none":
            evidence_count += 1
        if signal_rank[sig] > signal_rank[best]:
            best = sig
        all_codes.update(codes)
        all_phrases.update(phrases)

    return SafetyNettingMatch(
        recorded=best in ("strong", "medium"),
        signal=best,
        code_hits=tuple(sorted(all_codes)),
        phrase_hits=tuple(sorted(all_phrases)),
        evidence_count=evidence_count,
    )


__all__ = [
    "SafetyNettingMatch",
    "SafetyNettingSignal",
    "detect_safety_netting",
]
