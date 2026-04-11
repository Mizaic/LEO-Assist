"""Feed audit surface-form gaps into the SurfaceFormTask review queue.

Reads surface_form_gaps_valid.json (pre-triaged) or surface_form_gaps.json
and creates SurfaceFormTask nodes. Uses two tracks:

  Track A -- Observable entity lab terms (short phrases, semantic_tag =
             Observable_entity). The resolver commonly fails these because it
             picks up the stripped unit instead of the test name. We trust
             the LLM audit's expected_snomed for these.
             Source tag: "audit_gap_lab"

  Track B -- Clinical finding / procedure / situation short phrases where the
             resolver found something at wrong rank (gap_type = wrong_rank)
             and the resolver score is >= threshold. The expected_snomed from
             the LLM audit is used as the suggested concept.
             Source tag: "audit_gap_clinical"

Rejected outright:
  - Full sentences (>= 7 words or > 80 chars or sentence-starter patterns)
  - Score == 1.0 with nonsensical resolver result (resolver confusion)
  - Any entry where expected_snomed is missing
  - gap_type = not_found for clinical phrases (low confidence without resolver
    confirmation)

Idempotent: existing tasks are skipped.

Usage
-----
    python scripts/feed_audit_gaps_to_surface_forms.py --dry-run
    python scripts/feed_audit_gaps_to_surface_forms.py
    python scripts/feed_audit_gaps_to_surface_forms.py --audit-dir path/to/dir
    python scripts/feed_audit_gaps_to_surface_forms.py --threshold 0.80
    python scripts/feed_audit_gaps_to_surface_forms.py --track A
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402
from libs.cypher.surface_form_task_queries import (  # noqa: E402
    COUNT_SURFACE_FORM_TASKS,
    UPSERT_SURFACE_FORM_TASK,
    make_surface_form_task_id,
)
from libs.terminology.surface_normalize import strip_observable_value  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("feed_audit_gaps")

_DEFAULT_AUDIT_DIR = ROOT / "scripts" / "investigations" / "encounter_audit"

# -- Phrase quality thresholds -----------------------------------------------

_MAX_ENTITY_CHARS = 80

# Track A (lab observable entities): lab test abbreviations and names are
# almost always <= 4 words. "Serum alkaline phosphatase level" is 4 words.
# 5 allows "Haemoglobin A1c - IFCC" as a borderline case.
_MAX_WORDS_TRACK_A = 5

# Track B (clinical phrases): short terms only. Longer phrases are sentences.
_MAX_WORDS_TRACK_B = 4

# Score 1.0 in the gaps file is a resolver confusion artefact (not confidence).
# Examples: "MRI on ICE" -> "Fall on ice", "See FIT >200" -> "Holy See".
_ANOMALOUS_SCORE = 1.0

# Track B minimum score: require a reliable resolver match at wrong rank.
_TRACK_B_MIN_SCORE = 0.80

# After strip_observable_value, residual digits indicate the value was not
# fully removed (e.g. "eGFR 73", "hb 106", "recent TSH was 2.7").
# These are not valid surface forms.
_RESIDUAL_DIGIT_RE = re.compile(r"\b\d+\b")

# Verbs and behavioural words that indicate narrative/activity descriptions,
# not lab test names. Used to block Track A behavioural phrases.
_BEHAVIOUR_VERBS = frozenset(
    {
        "goes",
        "going",
        "go",
        "attends",
        "attending",
        "attend",
        "walks",
        "walking",
        "walk",
        "exercises",
        "exercising",
        "exercise",
        "engages",
        "engaging",
        "participates",
        "participating",
        "reports",
        "experiencing",
        "experienced",
        "diagnosed",
        "seen",
        "seeing",
        "said",
        "told",
        "noted",
        "documented",
    }
)

# Sentence-starter patterns that identify narrative text, not surface forms.
_SENTENCE_STARTERS = (
    "patient ",
    "patients ",
    "reports ",
    "reporting ",
    "experiencing ",
    "experienced ",
    "diagnosed ",
    "has been ",
    "have been ",
    "i am ",
    "i have ",
    "an urgent ",
    "a ct ",
    "a mri ",
    "an mri ",
    "an ultrasound ",
    "a ultrasound ",
    "daytime ",
    "active symptom ",
    "seen at ",
    "following your ",
    "will need ",
    "was diagnosed ",
    "telephone call ",
    "e-mail ",
    "email ",
    "some weight",
    "had outpatient",
    "recent cxr reported",
    "queried about",
)

_ADMIN_PATTERNS = (
    "entered at:",
    "care started",
    "care ended",
    "llr spa",
    "lll spa",
    "woodbrook medical centre",
    "university hospitals of leicester",
    "admission to",
    "ambulance service",
    "receptionist access role",
    "surgery: ",
    "it will take place by phone",
    "video or in person as agreed",
    "arrived at property",
    "greeted by",
    "son ",
    "daughter ",
    "husband ",
    "wife ",
    "kevin",
    "rtf:",
    # Admin/system-generated phrases
    "request (",
    "pathology request",
    "requested)",
    # Planned / future-action phrases -- not clinical findings
    "to be completed",
    "to be done",
    "awaiting results",
    "including fit",
    "await further",
    # Generic / non-specific phrases that leaked through LLM audit
    "improvement to",
)

_OBSERVABLE_TAG = "Observable_entity"
_CLINICAL_TAGS = {
    "Clinical_finding",
    "Procedure",
    "Situation",
    "Disorder",
    "Body_structure",
    "Pharmaceutical___biologic_product",
}

# -- Cypher duplicate check --------------------------------------------------

_CHECK_TASK_EXISTS = """
MATCH (t:SurfaceFormTask)
WHERE t.entity_text = $entity_text
  AND t.suggested_concept = $suggested_concept
  AND t.status IN ['pending', 'approved']
RETURN count(t) AS n
"""


# -- Classification helpers --------------------------------------------------


def _is_sentence(text: str) -> bool:
    """Return True if the text looks like narrative prose, not a surface form."""
    if len(text) > _MAX_ENTITY_CHARS:
        return True
    words = text.split()
    if len(words) >= 7:
        return True
    # Commas indicate list/compound phrases -- never a valid surface form.
    if "," in text:
        return True
    low = text.lower()
    return any(low.startswith(p) for p in _SENTENCE_STARTERS)


def _is_admin(text: str) -> bool:
    low = text.lower()
    return any(pat in low for pat in _ADMIN_PATTERNS)


def _has_residual_digit(text: str) -> bool:
    """Return True if text still contains a bare digit after value stripping.

    Catches cases where strip_observable_value could not strip the value
    because it lacked a recognised unit (e.g. 'eGFR 73', 'hb 106').
    Allows alphanumeric codes like 'T4', 'B12', 'IgA', 'HbA1c'.
    """
    return bool(_RESIDUAL_DIGIT_RE.search(text))


def _has_behaviour_verb(text: str) -> bool:
    """Return True if any word in the text is a behavioural verb."""
    words = {w.lower().strip(".,;:") for w in text.split()}
    return bool(words & _BEHAVIOUR_VERBS)


def _classify_gap(gap: dict[str, Any], threshold: float) -> str | None:
    """Return 'A', 'B', or None (reject).

    'A' -- Observable entity lab term: trust expected_snomed directly.
    'B' -- Clinical phrase with resolver confirmation at wrong rank.
    None -- Reject.
    """
    evidence = str(gap.get("evidence") or "").strip()
    expected_snomed = str(gap.get("expected_snomed") or "").strip()
    semantic_tag = str(gap.get("semantic_tag") or "")
    gap_type = str(gap.get("gap_type") or "")
    score = float(gap.get("resolver_top_score") or 0.0)

    if not evidence or not expected_snomed:
        return None
    if len(evidence) <= 1:
        return None
    if _is_sentence(evidence):
        return None
    if _is_admin(evidence):
        return None
    if score == _ANOMALOUS_SCORE:
        return None
    if _has_residual_digit(evidence):
        return None

    word_count = len(evidence.split())

    if semantic_tag == _OBSERVABLE_TAG:
        if word_count > _MAX_WORDS_TRACK_A:
            return None
        if _has_behaviour_verb(evidence):
            return None
        return "A"

    if semantic_tag in _CLINICAL_TAGS:
        if word_count > _MAX_WORDS_TRACK_B:
            return None
        if _has_behaviour_verb(evidence):
            return None
        if gap_type == "wrong_rank" and score >= _TRACK_B_MIN_SCORE:
            return "B"

    return None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _task_exists(session, entity_text: str, suggested_concept: str) -> bool:
    row = session.run(
        _CHECK_TASK_EXISTS,
        entity_text=entity_text,
        suggested_concept=suggested_concept,
    ).single()
    return bool(row and row["n"] > 0)


def _pending_count(session) -> int:
    row = session.run(COUNT_SURFACE_FORM_TASKS, status="pending").single()
    return int(row["total"]) if row else 0


# -- Core feed logic ---------------------------------------------------------


def feed_gaps(
    gaps: list[dict[str, Any]],
    threshold: float,
    dry_run: bool,
    tracks: set[str],
) -> dict[str, int]:
    counts: dict[str, int] = {
        "created_A": 0,
        "created_B": 0,
        "skipped_exists": 0,
        "rejected": 0,
    }

    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            for gap in gaps:
                # Strip lab values from evidence before classification.
                evidence = str(gap.get("evidence") or "").strip()
                evidence = strip_observable_value(evidence)
                gap = {**gap, "evidence": evidence}

                track = _classify_gap(gap, threshold)
                if track is None or track not in tracks:
                    counts["rejected"] += 1
                    continue

                expected_snomed = str(gap.get("expected_snomed") or "").strip()
                expected_name = str(gap.get("expected_name") or evidence).strip()
                score = float(gap.get("resolver_top_score") or 0.0)
                source = "audit_gap_lab" if track == "A" else "audit_gap_clinical"

                if dry_run:
                    logger.info(
                        "[DRY RUN] Track %s | %r -> %s (%s) score=%.2f",
                        track,
                        evidence,
                        expected_snomed,
                        expected_name[:50],
                        score,
                    )
                    counts[f"created_{track}"] += 1
                    continue

                if _task_exists(session, evidence, expected_snomed):
                    counts["skipped_exists"] += 1
                    continue

                normalized = _normalize(evidence)
                task_id = make_surface_form_task_id(
                    candidate_id="audit_gap",
                    entity_text=normalized,
                    current_concept=expected_snomed,
                )
                session.run(
                    UPSERT_SURFACE_FORM_TASK,
                    task_id=task_id,
                    entity_text=evidence,
                    current_concept="",
                    current_term="",
                    suggested_concept=expected_snomed,
                    suggested_term=expected_name,
                    candidates_json="[]",
                    context_text=str(gap.get("encounter_id") or ""),
                    candidate_id="",
                    confidence=score,
                    source=source,
                )
                logger.info(
                    "Created Task (track=%s): %r -> %s score=%.2f",
                    track,
                    evidence,
                    expected_snomed,
                    score,
                )
                counts[f"created_{track}"] += 1
    finally:
        client.close()
    return counts


# -- Entry point -------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Feed audit surface-form gaps to review queue"
    )
    parser.add_argument(
        "--audit-dir",
        default=str(_DEFAULT_AUDIT_DIR),
        metavar="DIR",
        help="Directory containing surface_form_gaps_valid.json",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=_TRACK_B_MIN_SCORE,
        metavar="SCORE",
        help=f"Minimum resolver score for Track B clinical phrases (default {_TRACK_B_MIN_SCORE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing to Neo4j",
    )
    parser.add_argument(
        "--track",
        choices=["A", "B", "both"],
        default="both",
        help="Which track to process: A (lab/observable), B (clinical), both (default)",
    )
    args = parser.parse_args()

    tracks = {"A", "B"} if args.track == "both" else {args.track}

    audit_dir = Path(args.audit_dir)
    gaps_file = audit_dir / "surface_form_gaps_valid.json"
    if not gaps_file.exists():
        gaps_file = audit_dir / "surface_form_gaps.json"
        logger.warning(
            "surface_form_gaps_valid.json not found -- falling back to raw "
            "surface_form_gaps.json (run _triage_surface_gaps.py first for "
            "cleaner results)"
        )
    if not gaps_file.exists():
        logger.error("No surface_form_gaps file found at %s", audit_dir)
        sys.exit(1)

    gaps = json.loads(gaps_file.read_text(encoding="utf-8"))
    logger.info("Loaded %d surface-form gaps from %s", len(gaps), gaps_file)
    logger.info(
        "Tracks: %s  Threshold: %.2f  Dry-run: %s", tracks, args.threshold, args.dry_run
    )

    counts = feed_gaps(
        gaps, threshold=args.threshold, dry_run=args.dry_run, tracks=tracks
    )
    total_created = counts["created_A"] + counts["created_B"]
    logger.info(
        "Complete. Track-A=%d  Track-B=%d  skipped(exists)=%d  rejected=%d  TOTAL_CREATED=%d",
        counts["created_A"],
        counts["created_B"],
        counts["skipped_exists"],
        counts["rejected"],
        total_created,
    )


if __name__ == "__main__":
    main()
