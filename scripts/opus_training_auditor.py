"""Opus-in-the-Loop TrainingLabel auditor.

Uses Claude Opus 4.6 (AWS_MAX_MODEL) to review every included
TrainingLabel record, validating entities, assertions, values, SNOMED
codes, and span boundaries.  Applies safe auto-fixes and escalates
ambiguous issues for human review.

Usage
-----
    # Dry-run (default) — audit only, no writes:
    python -m scripts.opus_training_auditor --limit 50

    # Apply safe auto-fixes:
    python -m scripts.opus_training_auditor --apply

    # Skip already-audited records on re-run:
    python -m scripts.opus_training_auditor --skip-audited --apply

    # Full options:
    python -m scripts.opus_training_auditor \\
        --limit 500 --offset 0 --apply --skip-audited

Environment variables
---------------------
    OPUS_AUDIT_WORKERS     Thread pool size (default: 5).
    NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
    AWS_DEFAULT_REGION     Bedrock region.
    AWS_MAX_MODEL          Override Opus model ID.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

_SECRETS = _REPO_ROOT / "secrets"
load_dotenv(_SECRETS / ".env.config", override=True)
load_dotenv(_SECRETS / ".env", override=False)

from libs.llm_client.factory import create_llm, LLMClient, LLMResponse
from libs.llm_client.prompt_safety import INJECTION_GUARD, sanitise_for_prompt
from libs.neo4j_client.client import PatientGraphClient
from libs.prompts.registry import get_prompt
from services.coding_worker.app.pipeline.sentence_splitter import SentenceSplitter, SentenceChunk

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("opus_training_auditor")

# ── Configuration ─────────────────────────────────────────────────────────────
MAX_WORKERS = int(os.getenv("OPUS_AUDIT_WORKERS", "5"))

SAFE_FIX_FIELDS = frozenset({
    "text",
    "assertion",
    "value", "unit", "reference_range",
    "label",
    "normalized",
})

SAFE_FIX_CONFIDENCE = 0.95

AUTOFIX_CAP_WINDOW = 100
AUTOFIX_CAP_RATIO = 0.30

# ── Cypher ────────────────────────────────────────────────────────────────────
FETCH_AUDIT_LABELS = """
MATCH (t:TrainingLabel)
WHERE t.include = true
  AND t.text IS NOT NULL
  AND t.entities_json IS NOT NULL
  {skip_audited_clause}
RETURN
    t.label_id       AS label_id,
    t.encounter_id   AS encounter_id,
    t.text           AS text,
    t.entities_json  AS entities_json,
    t.source         AS source,
    coalesce(t.quality_score, 0.0) AS quality_score
ORDER BY t.created_at ASC
{limit_clause}
{offset_clause}
"""

SET_AUDITED_AT = """
MATCH (t:TrainingLabel {label_id: $label_id})
SET t.audited_at = datetime()
RETURN t.label_id AS label_id
"""

UPDATE_ENTITIES = """
MATCH (t:TrainingLabel {label_id: $label_id})
SET t.entities_json = $entities_json,
    t.audited_at    = datetime(),
    t.updated_at    = datetime()
RETURN t.label_id AS label_id
"""


# ── Data structures ───────────────────────────────────────────────────────────
@dataclass
class AuditVerdict:
    label_id: str
    record_verdict: str
    entity_verdicts: list[dict[str, Any]]
    missing_entities: list[dict[str, Any]]
    auto_fixes_applied: list[dict[str, Any]] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


# ── Entity format normalisation ──────────────────────────────────────────────
def _normalise_entity(ent: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested 'coding' sub-object to top-level fields."""
    coding = ent.pop("coding", None)
    if isinstance(coding, dict):
        ent.setdefault("snomed_concept_id", coding.get("snomed_concept_id"))
        ent.setdefault("snomed_term", coding.get("snomed_term") or coding.get("term"))
        ent.setdefault("read_code", coding.get("read_code"))
        if "score" in coding and "snomed_score" not in ent:
            ent["snomed_score"] = coding["score"]
        if "semantic_tag" in coding and "label" not in ent:
            ent["label"] = coding["semantic_tag"]
    return ent


def _parse_entities(raw: str) -> list[dict[str, Any]]:
    """Parse entities_json string, normalising to flat format."""
    entities = json.loads(raw) if isinstance(raw, str) else raw
    return [_normalise_entity(e) for e in entities]


# ── JSON extraction from LLM response ────────────────────────────────────────
_JSON_KEYS = {"record_verdict", "entity_verdicts"}


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON object from LLM response, tolerating markdown fences."""
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    # Try markdown code block
    import re
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1).strip())
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise json.JSONDecodeError("No JSON object found in response", text, 0)


def _validate_verdict(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the Opus verdict against expected schema."""
    if not isinstance(data, dict):
        raise ValueError("Verdict must be a JSON object")
    if "record_verdict" not in data:
        raise ValueError("Missing 'record_verdict'")
    if data["record_verdict"] not in ("pass", "has_issues"):
        raise ValueError(f"Invalid record_verdict: {data['record_verdict']}")
    if "entity_verdicts" not in data or not isinstance(data["entity_verdicts"], list):
        raise ValueError("Missing or invalid 'entity_verdicts'")
    for ev in data["entity_verdicts"]:
        if "entity_index" not in ev:
            raise ValueError("entity_verdict missing 'entity_index'")
        if ev.get("verdict") not in ("correct", "fixable", "needs_review", "remove"):
            raise ValueError(f"Invalid verdict: {ev.get('verdict')}")
    data.setdefault("missing_entities", [])
    return data


# ── Sentence-aware context builder ───────────────────────────────────────────
_splitter: SentenceSplitter | None = None


def _get_splitter() -> SentenceSplitter:
    global _splitter
    if _splitter is None:
        _splitter = SentenceSplitter()
    return _splitter


def _assign_sentence_ids(
    entities: list[dict[str, Any]],
    sentences: list[SentenceChunk],
) -> list[dict[str, Any]]:
    """Return entities with a '__sentence_id' key indicating which sentence
    each entity belongs to, based on character offset overlap."""
    enriched = []
    for ent in entities:
        ent_start = int(ent.get("start") or 0)
        ent_end = int(ent.get("end") or 0)
        matched_id = None
        for sent in sentences:
            # Entity overlaps sentence if their ranges intersect
            if ent_start < sent.end and ent_end > sent.start:
                matched_id = sent.sentence_id
                break
        enriched.append({**ent, "__sentence_id": matched_id})
    return enriched


# ── Core audit logic ─────────────────────────────────────────────────────────
def _build_user_message(
    text: str,
    entities: list[dict[str, Any]],
    label_id: str,
    source: str,
    quality_score: float,
) -> str:
    splitter = _get_splitter()
    sentences = splitter.split(text)
    sentence_list = [
        {"sentence_id": s.sentence_id, "start": s.start, "end": s.end, "text": s.text}
        for s in sentences
    ]
    enriched_entities = _assign_sentence_ids(entities, sentences)

    return json.dumps({
        "label_id": label_id,
        "source": source,
        "quality_score": quality_score,
        "encounter_text": sanitise_for_prompt(text),
        "sentences": sentence_list,
        "entities_json": enriched_entities,
    }, indent=2)


def audit_record(
    client: LLMClient,
    system_prompt: str,
    row: dict[str, Any],
    max_retries: int = 3,
) -> AuditVerdict:
    """Send one TrainingLabel to Opus and parse the verdict."""
    label_id = row["label_id"]
    try:
        entities = _parse_entities(row["entities_json"])
    except (json.JSONDecodeError, TypeError) as exc:
        return AuditVerdict(
            label_id=label_id,
            record_verdict="error",
            entity_verdicts=[],
            missing_entities=[],
            error=f"entities_json parse error: {exc}",
        )

    user_msg = _build_user_message(
        text=row["text"],
        entities=entities,
        label_id=label_id,
        source=row.get("source", ""),
        quality_score=row.get("quality_score", 0.0),
    )

    last_error = ""
    for attempt in range(max_retries):
        try:
            resp: LLMResponse = client.converse(
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=4096,
                temperature=0.0,
            )
            parsed = _extract_json(resp.text)
            verdict_data = _validate_verdict(parsed)

            return AuditVerdict(
                label_id=label_id,
                record_verdict=verdict_data["record_verdict"],
                entity_verdicts=verdict_data["entity_verdicts"],
                missing_entities=verdict_data.get("missing_entities", []),
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                cached_tokens=resp.cached_input_tokens,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = f"Parse error (attempt {attempt + 1}): {exc}"
            logger.warning("%s for %s", last_error, label_id)
        except Exception as exc:
            last_error = f"LLM error (attempt {attempt + 1}): {exc}"
            logger.warning("%s for %s", last_error, label_id)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    return AuditVerdict(
        label_id=label_id,
        record_verdict="error",
        entity_verdicts=[],
        missing_entities=[],
        error=last_error,
    )


READONLY_FIELDS = frozenset({
    "start", "end",
    "snomed_concept_id", "snomed_term", "read_code", "snomed_score",
    "decision_tier", "tier_decision", "tier_reason",
    "__sentence_id",
})


# ── Auto-fix logic ───────────────────────────────────────────────────────────
def _classify_fixes(verdict: AuditVerdict) -> None:
    """Classify issues into auto_fixes_applied vs proposals."""
    for ev in verdict.entity_verdicts:
        if ev["verdict"] not in ("fixable", "remove"):
            continue
        for issue in ev.get("issues", []):
            field = issue.get("field", "")
            if field in READONLY_FIELDS or field.startswith("__"):
                verdict.proposals.append({
                    "entity_index": ev["entity_index"],
                    "verdict": "needs_review",
                    **issue,
                })
                continue
            entry = {
                "entity_index": ev["entity_index"],
                "verdict": ev["verdict"],
                **issue,
            }
            is_safe = (
                ev["verdict"] == "fixable"
                and field in SAFE_FIX_FIELDS
                and issue.get("confidence", 0) >= SAFE_FIX_CONFIDENCE
                and issue.get("suggested") is not None
            )
            if is_safe:
                verdict.auto_fixes_applied.append(entry)
            else:
                verdict.proposals.append(entry)

    for me in verdict.missing_entities:
        verdict.proposals.append({
            "entity_index": -1,
            "verdict": "missing",
            **me,
        })


def _apply_fixes(
    entities: list[dict[str, Any]],
    fixes: list[dict[str, Any]],
    encounter_text: str,
) -> list[dict[str, Any]]:
    """Apply safe auto-fixes to the entities list (returns a new copy).

    When the "text" field is changed, recomputes start/end offsets by
    searching for the new text in the encounter_text (same approach as
    the extraction pipeline's observable_post_processor).

    Strips audit-only keys (__sentence_id and any other __ prefixed keys)
    before returning so they are never written back to Neo4j.
    """
    entities = [dict(e) for e in entities]
    for fix in fixes:
        idx = fix.get("entity_index", -1)
        fld = fix.get("field")
        suggested = fix.get("suggested")
        if 0 <= idx < len(entities) and fld and suggested is not None:
            entities[idx][fld] = suggested
            if fld == "text" and isinstance(suggested, str):
                old_start = int(entities[idx].get("start") or 0)
                new_start = encounter_text.find(
                    suggested, max(0, old_start - 20)
                )
                if new_start < 0:
                    new_start = encounter_text.find(suggested)
                if new_start >= 0:
                    entities[idx]["start"] = new_start
                    entities[idx]["end"] = new_start + len(suggested)
    # Strip audit-only keys from all entities
    return [{k: v for k, v in e.items() if not k.startswith("__")} for e in entities]


# ── Audit trail (JSONL) ──────────────────────────────────────────────────────
def _write_trail_entry(
    trail_path: Path,
    verdict: AuditVerdict,
    applied: bool,
) -> None:
    entry = {
        "label_id": verdict.label_id,
        "record_verdict": verdict.record_verdict,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "applied": applied,
        "auto_fixes": verdict.auto_fixes_applied,
        "proposals": verdict.proposals,
        "missing_entities": verdict.missing_entities,
        "entity_verdicts": verdict.entity_verdicts,
        "input_tokens": verdict.input_tokens,
        "output_tokens": verdict.output_tokens,
        "cached_tokens": verdict.cached_tokens,
        "error": verdict.error,
    }
    with open(trail_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


# ── Auto-fix cap check ───────────────────────────────────────────────────────
class AutoFixCapMonitor:
    """Sliding-window monitor for auto-fix rate.  Pauses if > 30% of
    entities in the last N records received auto-fixes."""

    def __init__(self, window: int = AUTOFIX_CAP_WINDOW, ratio: float = AUTOFIX_CAP_RATIO):
        self._window = window
        self._ratio = ratio
        self._history: list[tuple[int, int]] = []  # (entity_count, fix_count)
        self.triggered = False

    def record(self, entity_count: int, fix_count: int) -> bool:
        self._history.append((entity_count, fix_count))
        if len(self._history) > self._window:
            self._history = self._history[-self._window:]
        total_entities = sum(e for e, _ in self._history)
        total_fixes = sum(f for _, f in self._history)
        if total_entities > 0 and total_fixes / total_entities > self._ratio:
            self.triggered = True
            return True
        return False


# ── Report generation ─────────────────────────────────────────────────────────
def _generate_report(
    verdicts: list[AuditVerdict],
    report_path: Path,
    applied: bool,
    elapsed_s: float,
) -> None:
    total = len(verdicts)
    errors = sum(1 for v in verdicts if v.error)
    passed = sum(1 for v in verdicts if v.record_verdict == "pass")
    has_issues = sum(1 for v in verdicts if v.record_verdict == "has_issues")

    verdict_counts: Counter[str] = Counter()
    for v in verdicts:
        for ev in v.entity_verdicts:
            verdict_counts[ev["verdict"]] += 1

    total_auto_fixes = sum(len(v.auto_fixes_applied) for v in verdicts)
    total_proposals = sum(len(v.proposals) for v in verdicts)

    total_input = sum(v.input_tokens for v in verdicts)
    total_output = sum(v.output_tokens for v in verdicts)
    total_cached = sum(v.cached_tokens for v in verdicts)

    # Field breakdown for auto-fixes
    fix_field_counts: Counter[str] = Counter()
    for v in verdicts:
        for fix in v.auto_fixes_applied:
            fix_field_counts[fix.get("field", "unknown")] += 1

    # Proposal breakdown
    proposal_type_counts: Counter[str] = Counter()
    for v in verdicts:
        for p in v.proposals:
            proposal_type_counts[p.get("verdict", "unknown")] += 1

    # Samples
    sample_fixes: list[dict] = []
    sample_proposals: list[dict] = []
    sample_reviews: list[dict] = []
    for v in verdicts:
        if len(sample_fixes) < 10:
            for fix in v.auto_fixes_applied:
                sample_fixes.append({"label_id": v.label_id, **fix})
                if len(sample_fixes) >= 10:
                    break
        if len(sample_proposals) < 10:
            for p in v.proposals:
                sample_proposals.append({"label_id": v.label_id, **p})
                if len(sample_proposals) >= 10:
                    break
        if len(sample_reviews) < 10:
            for ev in v.entity_verdicts:
                if ev["verdict"] == "needs_review":
                    sample_reviews.append({"label_id": v.label_id, **ev})
                    if len(sample_reviews) >= 10:
                        break

    lines = [
        "# Opus Training Label Audit Report",
        "",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Mode:** {'APPLY' if applied else 'DRY-RUN'}  ",
        f"**Records audited:** {total}  ",
        f"**Elapsed:** {elapsed_s:.0f}s ({elapsed_s / max(total, 1):.1f}s/record)  ",
        "",
        "## Summary",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Records passed | {passed} |",
        f"| Records with issues | {has_issues} |",
        f"| Errors (parse/LLM) | {errors} |",
        f"| Total auto-fixes | {total_auto_fixes} |",
        f"| Total proposals (human review) | {total_proposals} |",
        "",
        "## Entity Verdict Breakdown",
        "",
        "| Verdict | Count |",
        "|---------|-------|",
    ]
    for verdict_type in ("correct", "fixable", "needs_review", "remove"):
        lines.append(f"| {verdict_type} | {verdict_counts.get(verdict_type, 0)} |")
    lines.append("")

    if fix_field_counts:
        lines.extend([
            "## Auto-Fix Field Breakdown",
            "",
            "| Field | Count |",
            "|-------|-------|",
        ])
        for fld, cnt in fix_field_counts.most_common():
            lines.append(f"| {fld} | {cnt} |")
        lines.append("")

    if proposal_type_counts:
        lines.extend([
            "## Proposal Type Breakdown",
            "",
            "| Type | Count |",
            "|------|-------|",
        ])
        for ptype, cnt in proposal_type_counts.most_common():
            lines.append(f"| {ptype} | {cnt} |")
        lines.append("")

    lines.extend([
        "## Token Usage",
        "",
        f"| Metric | Tokens |",
        f"|--------|--------|",
        f"| Total input | {total_input:,} |",
        f"| Total output | {total_output:,} |",
        f"| Cached input | {total_cached:,} |",
        "",
    ])

    if sample_fixes:
        lines.extend([
            "## Sample Auto-Fixes (up to 10)",
            "",
        ])
        for sf in sample_fixes:
            lines.extend([
                f"- **{sf['label_id'][:12]}...** entity[{sf.get('entity_index')}] "
                f"`{sf.get('field')}`: `{sf.get('current')}` -> `{sf.get('suggested')}` "
                f"(conf={sf.get('confidence', 0):.2f}) — {sf.get('rationale', '')}",
            ])
        lines.append("")

    if sample_proposals:
        lines.extend([
            "## Sample Proposals for Human Review (up to 10)",
            "",
        ])
        for sp in sample_proposals:
            if sp.get("verdict") == "missing":
                lines.append(
                    f"- **{sp['label_id'][:12]}...** MISSING: `{sp.get('text')}` "
                    f"({sp.get('label')}, {sp.get('assertion')}) "
                    f"conf={sp.get('confidence', 0):.2f} — {sp.get('rationale', '')}"
                )
            else:
                lines.append(
                    f"- **{sp['label_id'][:12]}...** entity[{sp.get('entity_index')}] "
                    f"`{sp.get('field')}`: `{sp.get('current')}` -> `{sp.get('suggested')}` "
                    f"(conf={sp.get('confidence', 0):.2f}) — {sp.get('rationale', '')}"
                )
        lines.append("")

    if sample_reviews:
        lines.extend([
            "## Sample Needs-Review (up to 10)",
            "",
        ])
        for sr in sample_reviews:
            issues_str = "; ".join(
                f"{i.get('field')}: {i.get('rationale', '')}"
                for i in sr.get("issues", [])
            )
            lines.append(
                f"- **{sr['label_id'][:12]}...** entity[{sr.get('entity_index')}] "
                f"— {issues_str}"
            )
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Report written to %s", report_path)


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Opus-in-the-Loop TrainingLabel auditor"
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Max records to audit (0 = all)",
    )
    parser.add_argument(
        "--offset", type=int, default=0,
        help="Skip first N records",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Write safe auto-fixes to Neo4j (default: dry-run)",
    )
    parser.add_argument(
        "--skip-audited", action="store_true",
        help="Skip records that already have audited_at set",
    )
    parser.add_argument(
        "--workers", type=int, default=MAX_WORKERS,
        help=f"Thread pool size (default: {MAX_WORKERS})",
    )
    args = parser.parse_args()

    mode_label = "APPLY" if args.apply else "DRY-RUN"
    logger.info("=== Opus Training Label Auditor [%s] ===", mode_label)

    # Build query
    skip_clause = "AND t.audited_at IS NULL" if args.skip_audited else ""
    limit_clause = f"LIMIT {args.limit}" if args.limit else ""
    offset_clause = f"SKIP {args.offset}" if args.offset else ""
    query = FETCH_AUDIT_LABELS.format(
        skip_audited_clause=skip_clause,
        limit_clause=limit_clause,
        offset_clause=offset_clause,
    )

    # Connect
    neo4j = PatientGraphClient()
    try:
        rows = neo4j.run(query)
    except Exception as exc:
        logger.error("Failed to fetch TrainingLabels: %s", exc)
        sys.exit(1)

    total = len(rows)
    logger.info("Fetched %d records to audit", total)
    if total == 0:
        logger.info("Nothing to audit — exiting.")
        neo4j.close()
        return

    # Initialise sentence splitter eagerly (spaCy/PyRuSH load is not thread-safe)
    logger.info("Initialising sentence splitter...")
    _get_splitter()
    logger.info("Sentence splitter ready (mode: %s)", _get_splitter().mode)

    # Prepare LLM client and prompt
    llm = create_llm(provider="aws", tier="max")
    system_prompt = INJECTION_GUARD + get_prompt("opus_audit", version=1)
    logger.info("Using model: %s", llm.model_id)

    # Output paths
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    scripts_dir = Path(__file__).resolve().parent
    trail_path = scripts_dir / f"opus_audit_trail_{ts}.jsonl"
    report_path = scripts_dir / f"opus_audit_report_{ts}.md"

    verdicts: list[AuditVerdict] = []
    cap_monitor = AutoFixCapMonitor()
    cap_triggered_at: int | None = None
    t_start = time.monotonic()

    def _process_one(row: dict[str, Any]) -> AuditVerdict:
        return audit_record(llm, system_prompt, row)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_to_row = {
            pool.submit(_process_one, row): row for row in rows
        }
        for i, future in enumerate(as_completed(future_to_row), 1):
            row = future_to_row[future]
            label_id = row["label_id"]

            try:
                verdict = future.result()
            except Exception as exc:
                verdict = AuditVerdict(
                    label_id=label_id,
                    record_verdict="error",
                    entity_verdicts=[],
                    missing_entities=[],
                    error=str(exc),
                )

            _classify_fixes(verdict)

            # Auto-fix cap check
            try:
                entities = _parse_entities(row["entities_json"])
                entity_count = len(entities)
            except Exception:
                entity_count = 0
            fix_count = len(verdict.auto_fixes_applied)

            if cap_monitor.record(entity_count, fix_count) and cap_triggered_at is None:
                cap_triggered_at = i
                logger.warning(
                    "AUTO-FIX CAP TRIGGERED at record %d/%d — "
                    ">%.0f%% of entities in last %d records received auto-fixes. "
                    "Continuing audit but SUSPENDING auto-fix writes.",
                    i, total, cap_monitor._ratio * 100, cap_monitor._window,
                )

            # Write to Neo4j
            applied_this_record = False
            if args.apply and verdict.auto_fixes_applied and cap_triggered_at is None:
                try:
                    fixed_entities = _apply_fixes(entities, verdict.auto_fixes_applied, row["text"])
                    neo4j.run(
                        UPDATE_ENTITIES,
                        label_id=label_id,
                        entities_json=json.dumps(fixed_entities),
                    )
                    applied_this_record = True
                except Exception as exc:
                    logger.error("Failed to write fixes for %s: %s", label_id, exc)
            else:
                # Mark as audited even without fixes
                try:
                    neo4j.run(SET_AUDITED_AT, label_id=label_id)
                except Exception as exc:
                    logger.warning("Failed to set audited_at for %s: %s", label_id, exc)

            _write_trail_entry(trail_path, verdict, applied=applied_this_record)
            verdicts.append(verdict)

            if i % 50 == 0 or i == total:
                elapsed = time.monotonic() - t_start
                rate = i / elapsed if elapsed > 0 else 0
                logger.info(
                    "Progress: %d/%d (%.1f rec/s) | pass=%d issues=%d errors=%d fixes=%d proposals=%d",
                    i, total, rate,
                    sum(1 for v in verdicts if v.record_verdict == "pass"),
                    sum(1 for v in verdicts if v.record_verdict == "has_issues"),
                    sum(1 for v in verdicts if v.error),
                    sum(len(v.auto_fixes_applied) for v in verdicts),
                    sum(len(v.proposals) for v in verdicts),
                )

    elapsed_s = time.monotonic() - t_start
    logger.info("Audit complete in %.0fs", elapsed_s)

    _generate_report(verdicts, report_path, applied=args.apply, elapsed_s=elapsed_s)
    logger.info("Audit trail: %s", trail_path)

    if cap_triggered_at is not None:
        logger.warning(
            "AUTO-FIX CAP was triggered at record %d. Review the audit trail "
            "for systemic issues before re-running with --apply.",
            cap_triggered_at,
        )

    neo4j.close()


if __name__ == "__main__":
    main()
