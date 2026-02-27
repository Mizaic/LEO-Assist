"""Phase 1 — Anchor Audit Script.

Runs the three-tier anchor detector (SNOMED concepts → hybrid terminology →
optional regex) against every patient in the graph, then performs a deep-dive
investigation for any missing milestones using date-windowed encounter
scanning.

Deep mode (default, --no-deep to disable)
-----------------------------------------
When running in deep mode (the default for auditing), the script activates:
  • SNOMED IS_A hierarchy expansion — subtypes like "invasive ductal carcinoma"
    automatically match parent milestone concept IDs.
  • LLM disambiguation — a small LLM classifies each candidate hit as
    confirmed / suspected / historical / irrelevant, replacing naive regex
    context confidence.
  • Resolver-based investigation — when a milestone is missing, the hybrid
    resolver (exact + fulltext + vector) searches each candidate encounter to
    confirm or rule out the milestone, with LLM classification of hits.
  • Tier-3 regex suppressed — the legacy regex fallback is not used; the
    resolver + LLM provide better signal without hand-crafted patterns.

Output
------
exports/anchor_audit_<timestamp>.jsonl   one JSON object per patient
exports/anchor_audit_<timestamp>_summary.csv   one row per patient

VnV statistics are printed to stdout at the end and written to the summary
CSV header block.  They feed directly into Phase 3 (vnv_anchor_report.py)
after a clinician manually labels the borderline rows.

Labelling instructions
----------------------
After this script finishes, open the JSONL output and find rows where any
``investigation.<milestone>.assessment`` is ``found_soft`` or
``possibly_missing``.  Fill in the three fields:

    "manual_label": one of TRUE_POSITIVE | FALSE_NEGATIVE | TRUE_NEGATIVE | NOT_APPLICABLE
    "labelled_by":  reviewer name
    "labelled_at":  ISO date (YYYY-MM-DD)

Save as ``anchor_audit_<timestamp>_labelled.jsonl`` and run
``scripts/vnv_anchor_report.py --input <labelled file>`` for formal metrics.

Usage
-----
    python scripts/audit_patient_anchors.py
    python scripts/audit_patient_anchors.py --patients 4203796334,9876543210
    python scripts/audit_patient_anchors.py --limit 50 --no-hybrid
    python scripts/audit_patient_anchors.py --no-deep   # disable LLM + hierarchy expansion
    python scripts/audit_patient_anchors.py --resume --output-dir exports/
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime
import json
import logging
import os
import sys
import textwrap
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)
logger = logging.getLogger("anchor_audit")

# ─── constants ───────────────────────────────────────────────────────────────

ALL_MILESTONES = ["referral", "diagnosis", "treatment_start", "specialist_visit"]

# Default clinical windows (days) for missing-milestone investigations
_DEFAULT_WINDOWS: dict[str, dict[str, tuple[int, int]]] = {
    # (days_before_anchor, days_after_anchor)
    "diagnosis":        {"referral":  (30, 180), "all": (0, 0)},
    "specialist_visit": {"referral":  (0, 90),   "all": (0, 0)},
    "treatment_start":  {"diagnosis": (30, 365),  "all": (0, 0)},
}

SNIPPET_LEN = 200   # chars of encounter text to include in candidates
TOP_CANDIDATES = 5  # max candidates per missing milestone per patient


# ─── Neo4j helpers ───────────────────────────────────────────────────────────

def _get_patient_client():
    from libs.neo4j_client.client import PatientGraphClient
    return PatientGraphClient()


def _get_kg_client():
    from libs.neo4j_client.client import KnowledgeGraphClient
    return KnowledgeGraphClient()


def get_all_patients(client) -> list[dict[str, Any]]:
    """Return [{patient_id, enc_count}] ordered by enc_count desc."""
    return client.run(
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
        "WITH p, count(e) AS enc_count "
        "RETURN toString(p.id) AS patient_id, enc_count "
        "ORDER BY enc_count DESC",
    )


def get_patient_date_range(patient_id: str, client) -> tuple[str, str]:
    """Return (min_date, max_date) for a patient's encounters."""
    rows = client.run(
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
        "WHERE toString(p.id) = $pid AND e.date IS NOT NULL "
        "RETURN min(toString(e.date)) AS min_d, max(toString(e.date)) AS max_d",
        pid=patient_id,
    )
    if rows:
        return (rows[0].get("min_d") or "2000-01-01", rows[0].get("max_d") or "2030-12-31")
    return ("2000-01-01", "2030-12-31")


def get_encounters_in_window(
    patient_id: str,
    start: str,
    end: str,
    client,
) -> list[dict[str, Any]]:
    """Fetch all encounters for a patient within [start, end], with text."""
    return client.run(
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
        "WHERE toString(p.id) = $pid "
        "  AND toString(e.date) >= $start "
        "  AND toString(e.date) <= $end "
        "RETURN toString(e.id) AS encounter_id, "
        "       toString(e.date) AS date, "
        "       coalesce(e.text, e.flags, '') AS text "
        "ORDER BY e.date ASC",
        pid=patient_id, start=start, end=end,
    )


# ─── Encounter scoring ───────────────────────────────────────────────────────

# Imported lazily inside functions that need it to avoid circular imports
def _get_milestone_keywords() -> dict[str, list[str]]:
    from services.analysis_worker.app.analyzers.hybrid_anchor_search import MILESTONE_KEYWORDS
    return MILESTONE_KEYWORDS


def score_encounter_for_milestone(
    text: str,
    milestone_type: str,
    deep_mode: bool = False,
) -> tuple[float, str]:
    """Score encounter text for relevance to a milestone type.

    Uses sentence splitting rather than keyword-windowing — every sentence is
    evaluated, so subtle expressions are not missed because a predefined keyword
    was absent.

    In ``deep_mode``, the best candidate sentence is classified by LLM instead
    of regex context heuristics, giving a more accurate signal.

    Returns
    -------
    (score, context_signal)
        score          0.0 – 1.0
        context_signal "confirmed" | "suspected" | "ambiguous" | "none"
    """
    from services.analysis_worker.app.analyzers.hybrid_anchor_search import (
        CONFIRMED_RE,
        SUSPECTED_RE,
        AMBIGUOUS_RE,
        split_sentences,
        disambiguate_llm,
    )

    if not text:
        return 0.0, "none"

    sentences = split_sentences(text)
    keywords = _get_milestone_keywords().get(milestone_type, [])

    relevant = [
        s for s in sentences
        if any(kw in s.lower() for kw in keywords)
    ]
    if not relevant:
        return 0.0, "none"

    # Density: relevant sentences / total sentences, capped at 1.0
    density = min(1.0, len(relevant) / max(1, len(sentences)))

    if deep_mode:
        # LLM-classify the most keyword-dense sentence
        best = max(
            relevant,
            key=lambda s: sum(1 for kw in keywords if kw in s.lower()),
        )
        label = disambiguate_llm(best, milestone_type + " milestone", milestone_type)
        _signal_map = {
            "confirmed":  ("confirmed",  density),
            "suspected":  ("suspected",  density * 0.35),
            "historical": ("ambiguous",  density * 0.5),
            "irrelevant": ("none",       0.0),
        }
        signal, score = _signal_map.get(label, ("none", 0.0))
        return score, signal

    # Production: regex context heuristics
    full_text = text  # check full text for broader context signals
    if milestone_type == "diagnosis":
        if CONFIRMED_RE.search(full_text):
            return density, "confirmed"
        if SUSPECTED_RE.search(full_text):
            return density * 0.45, "suspected"
        if AMBIGUOUS_RE.search(full_text):
            return density * 0.75, "ambiguous"
        return density * 0.85, "ambiguous"

    return density, "confirmed"


# ─── Clinical window computation ─────────────────────────────────────────────

def _add_days(date_str: str, days: int) -> str:
    dt = datetime.date.fromisoformat(date_str[:10])
    return (dt + datetime.timedelta(days=days)).isoformat()


def compute_investigation_window(
    milestone_type: str,
    anchors: dict[str, list],
    patient_start: str,
    patient_end: str,
    override_days: int | None = None,
) -> tuple[str, str]:
    """Return (window_start, window_end) for investigating a missing milestone.

    Uses clinical logic (referral → diagnosis → treatment) if anchors for
    upstream milestones are available.  ``override_days`` replaces all
    per-milestone defaults.
    """
    if override_days:
        # symmetric window around now — use patient's full range
        return patient_start, patient_end

    cfg = _DEFAULT_WINDOWS.get(milestone_type, {})

    if milestone_type == "diagnosis":
        ref_anchors = anchors.get("referral", [])
        if ref_anchors:
            ref_date = ref_anchors[0]["encounter_date"][:10]
            before, after = cfg.get("referral", (30, 180))
            return _add_days(ref_date, -before), _add_days(ref_date, after)
        return patient_start, patient_end

    if milestone_type == "specialist_visit":
        ref_anchors = anchors.get("referral", [])
        if ref_anchors:
            ref_date = ref_anchors[0]["encounter_date"][:10]
            before, after = cfg.get("referral", (0, 90))
            return _add_days(ref_date, -before), _add_days(ref_date, after)
        return patient_start, patient_end

    if milestone_type == "treatment_start":
        diag_anchors = anchors.get("diagnosis", [])
        if diag_anchors:
            diag_date = diag_anchors[0]["encounter_date"][:10]
            before, after = cfg.get("diagnosis", (30, 365))
            return _add_days(diag_date, -before), _add_days(diag_date, after)
        return patient_start, patient_end

    # referral — scan everything
    return patient_start, patient_end


# ─── Deep investigation ──────────────────────────────────────────────────────

def _run_resolver_sync(sentences: list[str], expected_tag: str | None) -> dict:
    """Call the async resolver from a synchronous context via a thread.

    Creates a new event loop in a worker thread so this can be called safely
    even when a parent event loop is already running (e.g. inside asyncio.run).
    """
    import concurrent.futures
    from services.analysis_worker.app.analyzers.hybrid_anchor_search import (
        _resolve_sentences,
    )

    async def _call():
        return await _resolve_sentences(sentences, expected_tag)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, _call())
        try:
            return future.result(timeout=30)
        except Exception:
            logger.warning("_run_resolver_sync: resolver call timed out or failed")
            return {}


def investigate_missing(
    patient_id: str,
    milestone_type: str,
    anchors: dict[str, list],
    patient_start: str,
    patient_end: str,
    client,
    override_days: int | None = None,
    deep_mode: bool = False,
) -> dict[str, Any]:
    """Return an investigation block for a missing milestone.

    In ``deep_mode``:
    - Candidate snippets are the most relevant clinical sentences (not
      keyword-window fragments).
    - Resolver-based concept matching is run on top candidates with LLM
      disambiguation, giving a resolver_hit and LLM label per candidate.
    """
    from services.analysis_worker.app.analyzers.hybrid_anchor_search import (
        split_sentences,
        disambiguate_llm,
        _MILESTONE_EXPECTED_TAG,
    )

    win_start, win_end = compute_investigation_window(
        milestone_type, anchors, patient_start, patient_end, override_days
    )

    encounters = get_encounters_in_window(patient_id, win_start, win_end, client)

    scored: list[tuple[float, str, dict]] = []
    for enc in encounters:
        text = enc.get("text") or ""
        score, signal = score_encounter_for_milestone(text, milestone_type, deep_mode=deep_mode)
        if score > 0:
            scored.append((score, signal, enc))

    scored.sort(key=lambda x: -x[0])
    top = scored[:TOP_CANDIDATES]

    candidates = []
    for score, signal, enc in top:
        text = enc.get("text") or ""

        # Extract the best snippet using sentence splitting
        sentences = split_sentences(text)
        keywords = _get_milestone_keywords().get(milestone_type, [])
        # Pick the sentence with the most keyword hits as the snippet
        best_sentence = next(
            (s for s in sentences if any(kw in s.lower() for kw in keywords)),
            text[:SNIPPET_LEN],
        )
        snippet = best_sentence[:SNIPPET_LEN]

        entry: dict[str, Any] = {
            "encounter_id": str(enc.get("encounter_id", "")),
            "date": str(enc.get("date", "")),
            "snippet": snippet,
            "context_signal": signal,
            "keyword_score": round(score, 3),
        }

        # Deep mode: run resolver on relevant sentences and classify with LLM
        if deep_mode and sentences:
            relevant_sentences = [
                s for s in sentences
                if any(kw in s.lower() for kw in keywords)
            ][:5]  # top 5 sentences to resolver
            if relevant_sentences:
                expected_tag = _MILESTONE_EXPECTED_TAG.get(milestone_type)
                resolver_results = _run_resolver_sync(relevant_sentences, expected_tag)
                resolver_hits = []
                for sent, candidates_list in resolver_results.items():
                    for cand in (candidates_list or [])[:2]:
                        if cand.get("snomed_concept_id") and cand.get("score", 0) >= 0.4:
                            llm_label = disambiguate_llm(sent, cand.get("snomed_term", ""), milestone_type)
                            resolver_hits.append({
                                "sentence": sent[:200],
                                "snomed_id": cand["snomed_concept_id"],
                                "snomed_term": cand.get("snomed_term", ""),
                                "score": round(float(cand.get("score", 0)), 3),
                                "llm_label": llm_label,
                            })
                if resolver_hits:
                    entry["resolver_hits"] = sorted(
                        resolver_hits, key=lambda h: -h["score"]
                    )

        candidates.append(entry)

    # Determine assessment
    if not candidates:
        assessment = "truly_missing"
        notes = "No domain keyword hits in investigation window."
    else:
        best_signal = top[0][1]
        best_score  = top[0][0]
        if best_signal == "confirmed" and best_score >= 0.3:
            assessment = "found_soft"
            notes = (
                "Confirmed language present in encounter text but below "
                "concept/resolver threshold — likely a coding gap."
            )
        elif best_signal == "suspected":
            assessment = "possibly_missing"
            notes = (
                "Only suspected/pending language found — milestone may be "
                "legitimately absent from records (patient referred but not "
                "yet diagnosed, etc.)."
            )
        else:
            assessment = "possibly_missing"
            notes = (
                "Keyword hits but ambiguous or historical context — clinical "
                "review needed to confirm whether milestone occurred."
            )

    return {
        "window": [win_start, win_end],
        "encounters_scanned": len(encounters),
        "candidates": candidates,
        "assessment": assessment,
        "notes": notes,
        "manual_label": None,
        "labelled_by": None,
        "labelled_at": None,
    }


# ─── Per-patient audit ────────────────────────────────────────────────────────

def audit_patient(
    patient_id: str,
    enc_count: int,
    client,
    use_hybrid: bool = True,
    window_days: int | None = None,
    deep_mode: bool = True,
    kg_session=None,
) -> dict[str, Any]:
    """Run full audit for a single patient and return result dict.

    ``deep_mode=True`` (default) activates SNOMED hierarchy expansion and LLM
    disambiguation in anchor detection, and resolver-based investigation for
    missing milestones.  ``kg_session`` must be an open KnowledgeGraphClient
    session for SNOMED expansion to work; if None, hierarchy expansion is
    silently skipped.
    """
    from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors

    date_start, date_end = get_patient_date_range(patient_id, client)

    try:
        result = detect_anchors(
            patient_id=patient_id,
            start_date=date_start,
            end_date=date_end,
            patient_client=client,
            use_hybrid=use_hybrid,
            deep_mode=deep_mode,
            kg_session=kg_session,
        )
    except Exception:
        logger.exception("detect_anchors failed for patient %s", patient_id)
        return {
            "patient_id": patient_id,
            "encounter_count": enc_count,
            "error": "detect_anchors raised an exception",
        }

    anchors: dict[str, list] = {
        "referral":         result.referral_anchors,
        "diagnosis":        result.diagnosis_anchors,
        "treatment_start":  result.treatment_anchors,
        "specialist_visit": result.specialist_visit_anchors,
    }
    missing = [m for m, lst in anchors.items() if not lst]

    # Tier attribution per found milestone
    tier_breakdown: dict[str, str] = {}
    for milestone, lst in anchors.items():
        if not lst:
            tier_breakdown[milestone] = "missing"
        else:
            src = lst[0].get("source", "unknown")
            method = lst[0].get("detection_method", result.detection_method)
            tier_breakdown[milestone] = method or src

    # Deep investigation for missing milestones
    investigation: dict[str, Any] = {}
    for milestone in missing:
        investigation[milestone] = investigate_missing(
            patient_id=patient_id,
            milestone_type=milestone,
            anchors=anchors,
            patient_start=date_start,
            patient_end=date_end,
            client=client,
            override_days=window_days,
            deep_mode=deep_mode,
        )

    return {
        "patient_id": patient_id,
        "encounter_count": enc_count,
        "date_range": [date_start, date_end],
        "detection_method": result.detection_method,
        "anchors": anchors,
        "missing": missing,
        "investigation": investigation,
        "tier_breakdown": tier_breakdown,
    }


# ─── VnV statistics ──────────────────────────────────────────────────────────

def compute_vnv_stats(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute population-level VnV proxy statistics from audit results."""
    n_patients = len(results)
    n_encounters = sum(r.get("encounter_count", 0) for r in results)
    all_dates = [d for r in results for d in r.get("date_range", []) if d]
    date_from = min(all_dates) if all_dates else "n/a"
    date_to   = max(all_dates) if all_dates else "n/a"

    # Detection coverage per milestone
    coverage: dict[str, int] = {m: 0 for m in ALL_MILESTONES}
    complete_pathway = 0
    tier_counts: dict[str, dict[str, int]] = {
        m: {"concept": 0, "hybrid": 0, "concept+hybrid": 0, "regex": 0, "other": 0}
        for m in ALL_MILESTONES
    }
    assessment_counts: dict[str, dict[str, int]] = {
        m: {"found_soft": 0, "possibly_missing": 0, "truly_missing": 0}
        for m in ALL_MILESTONES
    }

    for r in results:
        if r.get("error"):
            continue
        anchors = r.get("anchors", {})
        found_all = True
        for m in ALL_MILESTONES:
            if anchors.get(m):
                coverage[m] += 1
                method = r.get("tier_breakdown", {}).get(m, "other")
                key = method if method in tier_counts[m] else "other"
                tier_counts[m][key] += 1
            else:
                found_all = False
                inv = r.get("investigation", {}).get(m, {})
                assess = inv.get("assessment", "truly_missing")
                if assess in assessment_counts[m]:
                    assessment_counts[m][assess] += 1

        if found_all:
            complete_pathway += 1

    stats: dict[str, Any] = {
        "population": {
            "patients": n_patients,
            "encounters": n_encounters,
            "date_from": date_from,
            "date_to": date_to,
            "median_enc_per_patient": (
                sorted(r.get("encounter_count", 0) for r in results)[n_patients // 2]
                if n_patients else 0
            ),
        },
        "detection_coverage": {
            m: {
                "found": coverage[m],
                "pct": round(coverage[m] / n_patients * 100, 1) if n_patients else 0,
            }
            for m in ALL_MILESTONES
        },
        "complete_pathway": {
            "count": complete_pathway,
            "pct": round(complete_pathway / n_patients * 100, 1) if n_patients else 0,
        },
        "tier_attribution": tier_counts,
        "false_negative_proxy": {
            m: assessment_counts[m]["found_soft"]
            for m in ALL_MILESTONES
        },
        "assessment_breakdown": assessment_counts,
    }
    return stats


def print_vnv_summary(stats: dict[str, Any]) -> None:
    pop = stats["population"]
    logger.info("=" * 70)
    logger.info("ANCHOR AUDIT — VnV STATISTICS SUMMARY")
    logger.info("  Patients:   %d", pop["patients"])
    logger.info("  Encounters: %d", pop["encounters"])
    logger.info("  Date range: %s → %s", pop["date_from"], pop["date_to"])
    logger.info("  Median enc/patient: %d", pop["median_enc_per_patient"])
    logger.info("-" * 70)
    logger.info("  Complete 4-milestone pathway: %d patients (%.1f%%)",
                stats["complete_pathway"]["count"],
                stats["complete_pathway"]["pct"])
    logger.info("-" * 70)
    for m in ALL_MILESTONES:
        cov = stats["detection_coverage"][m]
        tiers = stats["tier_attribution"][m]
        fn = stats["false_negative_proxy"][m]
        assmt = stats["assessment_breakdown"][m]
        logger.info(
            "  %-20s found=%d (%.0f%%)  tiers: concept=%d hybrid=%d regex=%d  "
            "found_soft=%d possibly_missing=%d truly_missing=%d",
            m, cov["found"], cov["pct"],
            tiers["concept"] + tiers.get("concept+hybrid", 0),
            tiers["hybrid"],
            tiers["regex"],
            fn, assmt["possibly_missing"], assmt["truly_missing"],
        )
    logger.info("=" * 70)
    logger.info(
        "  Labelling needed: rows with assessment 'found_soft' or "
        "'possibly_missing'.  Add manual_label / labelled_by / labelled_at "
        "then run scripts/vnv_anchor_report.py."
    )


# ─── Summary CSV ─────────────────────────────────────────────────────────────

def write_summary_csv(results: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "patient_id", "encounter_count", "date_from", "date_to",
        "detection_method", "missing_count",
        "referral", "diagnosis", "treatment_start", "specialist_visit",
        "referral_assessment", "diagnosis_assessment",
        "treatment_assessment", "specialist_assessment",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            if r.get("error"):
                writer.writerow({"patient_id": r["patient_id"], "detection_method": "ERROR"})
                continue
            anchors = r.get("anchors", {})
            inv = r.get("investigation", {})
            writer.writerow({
                "patient_id": r["patient_id"],
                "encounter_count": r.get("encounter_count", ""),
                "date_from": (r.get("date_range") or [""])[0],
                "date_to":   (r.get("date_range") or ["", ""])[1],
                "detection_method": r.get("detection_method", ""),
                "missing_count": len(r.get("missing", [])),
                "referral":        "found" if anchors.get("referral") else "missing",
                "diagnosis":       "found" if anchors.get("diagnosis") else "missing",
                "treatment_start": "found" if anchors.get("treatment_start") else "missing",
                "specialist_visit":"found" if anchors.get("specialist_visit") else "missing",
                "referral_assessment":    inv.get("referral", {}).get("assessment", ""),
                "diagnosis_assessment":   inv.get("diagnosis", {}).get("assessment", ""),
                "treatment_assessment":   inv.get("treatment_start", {}).get("assessment", ""),
                "specialist_assessment":  inv.get("specialist_visit", {}).get("assessment", ""),
            })
    logger.info("Summary CSV → %s", path)


# ─── Checkpointing ───────────────────────────────────────────────────────────

def load_existing_ids(jsonl_path: Path) -> set[str]:
    """Return set of patient_ids already present in an existing JSONL file."""
    if not jsonl_path.exists():
        return set()
    ids: set[str] = set()
    with jsonl_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    ids.add(json.loads(line)["patient_id"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return ids


# ─── Main ────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=textwrap.dedent("""\
            Anchor Audit — Phase 1 of ISO 13485 V&V.
            Runs three-tier anchor detection for every patient and produces
            a JSONL ground-truth file + VnV proxy statistics.
        """)
    )
    p.add_argument("--patients", help="Comma-separated patient IDs to audit (default: all)")
    p.add_argument("--limit", type=int, default=0,
                   help="Max patients to process (0 = all, default 0)")
    p.add_argument("--no-hybrid", action="store_true",
                   help="Skip tier-2 hybrid search (faster, text-only)")
    p.add_argument("--window-days", type=int, default=None,
                   help="Override per-milestone investigation windows (days)")
    p.add_argument("--output-dir", default="exports",
                   help="Directory for output files (default: exports/)")
    p.add_argument("--concurrency", type=int, default=1,
                   help="Number of patients to process concurrently (default 1)")
    p.add_argument("--verbose", action="store_true",
                   help="Log each encounter snippet during investigation")
    p.add_argument("--resume", action="store_true",
                   help="Skip patients already present in the output JSONL")
    p.add_argument("--no-deep", action="store_true",
                   help=(
                       "Disable deep-audit mode (SNOMED hierarchy expansion, LLM "
                       "disambiguation, resolver-based investigation).  Faster but "
                       "less thorough — not recommended for ground-truth audits."
                   ))
    return p.parse_args()


def main() -> int:
    args = parse_args()

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / f"anchor_audit_{ts}.jsonl"
    csv_path   = out_dir / f"anchor_audit_{ts}_summary.csv"

    # ── Patient list ──────────────────────────────────────────────────────
    client = _get_patient_client()
    try:
        if args.patients:
            all_rows = [
                {"patient_id": pid.strip(), "enc_count": 0}
                for pid in args.patients.split(",")
            ]
        else:
            all_rows = get_all_patients(client)
    finally:
        client.close()

    if args.limit:
        all_rows = all_rows[:args.limit]

    # Resume: filter out already-processed patients
    if args.resume:
        done_ids = load_existing_ids(jsonl_path)
        all_rows = [r for r in all_rows if r["patient_id"] not in done_ids]
        logger.info("Resume: %d patients left after skipping %d", len(all_rows), len(done_ids))

    deep_mode = not args.no_deep
    use_hybrid = not args.no_hybrid

    logger.info(
        "Audit starting: %d patients, hybrid=%s, deep_mode=%s, window_days=%s",
        len(all_rows), use_hybrid, deep_mode, args.window_days,
    )
    if deep_mode:
        logger.info(
            "Deep mode ON — SNOMED IS_A hierarchy expansion + LLM disambiguation "
            "+ resolver-based investigation.  Expect longer runtime per patient."
        )

    # Open KG client once for SNOMED hierarchy expansion (shared across workers)
    # The _fetch_expanded_sets function caches results after the first call.
    kg_client = _get_kg_client() if deep_mode else None

    results: list[dict[str, Any]] = []

    sem = asyncio.Semaphore(args.concurrency)

    async def _process_one(row: dict) -> dict:
        async with sem:
            pid = row["patient_id"]
            enc_count = row.get("enc_count", 0)
            c = _get_patient_client()
            try:
                # Open a KG session per patient for the IS_A traversal
                # (session is short-lived; expansion result is cached module-level)
                kg_session = None
                if kg_client is not None:
                    try:
                        kg_session = kg_client._driver.session()
                    except Exception:
                        logger.warning("Could not open KG session — hierarchy expansion disabled for %s", pid)
                try:
                    res = audit_patient(
                        pid, enc_count, c,
                        use_hybrid=use_hybrid,
                        window_days=args.window_days,
                        deep_mode=deep_mode,
                        kg_session=kg_session,
                    )
                finally:
                    if kg_session is not None:
                        try:
                            kg_session.close()
                        except Exception:
                            pass
            finally:
                c.close()
            logger.info(
                "  %s  enc=%d  missing=%s  method=%s",
                pid, enc_count,
                res.get("missing", []),
                res.get("detection_method", "?"),
            )
            # Append immediately so partial results survive crashes
            with jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(res, default=str) + "\n")
            return res

    async def _run_all():
        tasks = [_process_one(row) for row in all_rows]
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            res = await coro
            results.append(res)
            if i % 10 == 0:
                logger.info("Progress: %d / %d patients done", i, len(all_rows))

    asyncio.run(_run_all())

    if kg_client is not None:
        try:
            kg_client.close()
        except Exception:
            pass

    # ── VnV stats ─────────────────────────────────────────────────────────
    stats = compute_vnv_stats(results)
    print_vnv_summary(stats)

    stats_path = out_dir / f"anchor_audit_{ts}_vnv_stats.json"
    stats_path.write_text(json.dumps(stats, indent=2, default=str), encoding="utf-8")
    logger.info("VnV stats → %s", stats_path)

    write_summary_csv(results, csv_path)
    logger.info("JSONL output → %s  (%d rows)", jsonl_path, len(results))
    logger.info(
        "\nNext steps:\n"
        "  1. Open %s\n"
        "  2. Find rows where investigation.<milestone>.assessment is\n"
        "     'found_soft' or 'possibly_missing'\n"
        "  3. Add manual_label / labelled_by / labelled_at for each\n"
        "  4. Save as anchor_audit_%s_labelled.jsonl\n"
        "  5. Run: python scripts/vnv_anchor_report.py --input <labelled file>",
        jsonl_path, ts,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
