"""Audit-driven automated encounter remediation.

Reads audit findings from the SQLite checkpoint, verifies each proposed
change with a second Sonnet call, and applies confirmed fixes to Neo4j.

Usage
-----
    # Dry-run first to see what would change
    python scripts/remediate_audit_findings.py --dry-run

    # Run for real (all encounters)
    python scripts/remediate_audit_findings.py --yes

    # Critical missing only (fastest pass)
    python scripts/remediate_audit_findings.py --yes --severity critical

    # Resume after interruption
    python scripts/remediate_audit_findings.py --yes --resume

    # Single encounter for testing
    python scripts/remediate_audit_findings.py --yes --encounter <uuid>

Output
------
    scripts/investigations/encounter_audit/remediation.db  -- audit trail
    scripts/investigations/encounter_audit/disputes.jsonl  -- rejected changes
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from libs.cypher.documents_queries import _label_for_tag, _REL_BY_LABEL  # noqa: E402
from libs.cypher.remediation_queries import (  # noqa: E402
    GET_ENCOUNTER_FOR_REMEDIATION,
    DELETE_OVERCODED_DOCUMENTS,
    CLEANUP_PATIENT_SHORTCUT,
    GET_PATIENT_FOR_ENCOUNTER,
    UPDATE_DOCUMENTS_ASSERTION,
    build_add_documents_query,
)
from libs.llm_client.factory import create_llm  # noqa: E402
from libs.neo4j_client.client import PatientGraphClient  # noqa: E402
from libs.terminology.client import TerminologyClient  # noqa: E402
from scripts.investigations._audit_llm import _parse_json as _audit_parse_json  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("remediate")


def _parse_verify_json(raw: str) -> dict:
    """Extract the first valid JSON object from Sonnet's response.

    Handles 'Extra data' errors where Sonnet emits multiple JSON blocks
    or trailing text after the main object.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        inner = lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:]
        raw = "\n".join(inner).strip()
    # Find the first '{' and decode incrementally
    idx = raw.find("{")
    if idx == -1:
        raise ValueError(f"No JSON object found in: {raw[:200]}")
    raw = raw[idx:]
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(raw)
    return obj

AUDIT_DB = Path("scripts/investigations/encounter_audit/encounter_audit.db")
REM_DB = Path("scripts/investigations/encounter_audit/remediation.db")
DISPUTES_FILE = Path("scripts/investigations/encounter_audit/disputes.jsonl")
TERMINOLOGY_URL = "http://localhost:8001"
CONFIDENCE_THRESHOLD = 0.80

# SNOMED semantic tag words that may appear as trailing words in LLM search terms.
# Stripping these recovers many "not found" misses where the LLM appended the tag.
_SNOMED_TRAILING_TAGS = frozenset({
    "finding", "disorder", "situation", "procedure", "disease",
    "condition", "substance", "product", "observable",
})
_SNOMED_TRAILING_PAIRS = frozenset({
    "observable entity", "clinical finding", "regime therapy",
    "clinical situation", "qualifier value",
})

# Individual drug names the audit LLM should not flag, but in case it does,
# skip adding them as SNOMED clinical encounter codes.
_MEDICATION_BLOCKLIST_WORDS = frozenset({
    "metformin", "ramipril", "atorvastatin", "tirzepatide", "dapagliflozin",
    "sertraline", "doxycycline", "letrozole", "pregabalin", "gabapentin",
    "amlodipine", "bisoprolol", "lisinopril", "omeprazole", "lansoprazole",
    "simvastatin", "rosuvastatin", "levothyroxine", "salbutamol", "fluoxetine",
    "amitriptyline", "citalopram", "diclofenac", "naproxen", "codeine",
    "morphine", "oxycodone", "tramadol", "warfarin", "apixaban", "rivaroxaban",
    "aspirin", "clopidogrel", "furosemide", "spironolactone", "alendronic",
    "colecalciferol", "hydroxocobalamin", "erythromycin", "amoxicillin",
    "trimethoprim", "nitrofurantoin", "flucloxacillin", "cetirizine",
    "loratadine", "montelukast", "tiotropium", "salmeterol", "budesonide",
    "beclometasone", "prednisolone", "hydrocortisone", "methotrexate",
    "azathioprine", "hydroxychloroquine", "adalimumab", "etanercept",
    "insulin", "empagliflozin", "canagliflozin", "semaglutide", "liraglutide",
    "dulaglutide", "exenatide", "pioglitazone", "sitagliptin", "alogliptin",
    "tamsulosin", "finasteride", "dutasteride", "sildenafil", "tadalafil",
    "donepezil", "rivastigmine", "memantine", "quetiapine", "olanzapine",
    "risperidone", "aripiprazole", "mirtazapine", "venlafaxine", "duloxetine",
    "bupropion", "zopiclone", "zolpidem", "temazepam", "diazepam", "lorazepam",
    "levonorgestrel", "desogestrel", "norethisterone", "medroxyprogesterone",
})


def _is_medication_search(term: str) -> bool:
    """Return True if the search term appears to be a medication name."""
    words = term.lower().split()
    return bool(words and words[0] in _MEDICATION_BLOCKLIST_WORDS)


def _normalise_search_variants(term: str) -> list[str]:
    """Return search term variants with SNOMED semantic tags stripped.

    Tries the original term first, then with trailing tag words removed.
    This recovers terms like 'weight loss finding' -> 'weight loss'.
    """
    term = term.strip()
    candidates = [term]

    # Strip parenthetical tags: "Weight loss (finding)" -> "Weight loss"
    if "(" in term:
        clean = term[: term.rfind("(")].strip()
        if clean and clean not in candidates:
            candidates.append(clean)

    # Strip trailing two-word tag (e.g. "observable entity")
    lower = term.lower()
    for pair in _SNOMED_TRAILING_PAIRS:
        if lower.endswith(pair):
            stripped = term[: -(len(pair))].strip().rstrip(",").strip()
            if stripped and stripped not in candidates:
                candidates.append(stripped)

    # Strip trailing single-word tag (e.g. "finding", "disorder")
    parts = term.split()
    if len(parts) > 1 and parts[-1].lower() in _SNOMED_TRAILING_TAGS:
        stripped = " ".join(parts[:-1]).strip()
        if stripped and stripped not in candidates:
            candidates.append(stripped)

    return candidates


# Concepts already handled by _systematic_fixes.py -- skip in Sonnet pass
_ALREADY_FIXED_CONCEPTS = {
    "281900007",  # Normal appearance -- NAD, systematic delete done
    "185202000",  # Seen in GP surgery -- phone encounters, systematic delete done
}

# -- Verification system prompt (different from audit prompt) -----------------

_VERIFY_SYSTEM = """\
You are a clinical coding verifier for a UK GP practice using SNOMED CT.
An automated audit has proposed changes to the SNOMED coding of a GP
encounter note. Your task is to verify whether each proposed change is
clinically correct before it is committed to the patient record.

Be conservative: if you are not confident (confidence < 0.80), set agree=false.
Never agree to add a code that is NOT evidenced in the encounter text.
Never agree to delete a code that IS clearly evidenced in the encounter text.

ASSERTIONS:
  present   -- condition is active now
  historical -- was present in the past; not currently active
  absent    -- explicitly NOT present
  possible  -- uncertain, under investigation
  family    -- present in a family member only
  declined  -- patient declined an offer
  cancelled -- planned event did not proceed

Return ONLY valid JSON, no extra text:
{
  "verifications": [
    {
      "index": 0,
      "agree": true,
      "confidence": 0.95,
      "reason": "one sentence clinical justification"
    }
  ]
}
"""


# ---------------------------------------------------------------------------
# SQLite remediation DB
# ---------------------------------------------------------------------------


def _init_remediation_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS remediated (
            encounter_id    TEXT NOT NULL,
            action          TEXT NOT NULL,
            concept_id      TEXT NOT NULL,
            applied         INTEGER NOT NULL DEFAULT 0,
            old_value       TEXT,
            new_value       TEXT,
            sonnet_conf     REAL,
            sonnet_reason   TEXT,
            error_msg       TEXT,
            processed_at    TEXT NOT NULL,
            PRIMARY KEY (encounter_id, action, concept_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS enc_processed (
            encounter_id TEXT PRIMARY KEY,
            processed_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def _is_enc_done(conn: sqlite3.Connection, encounter_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM enc_processed WHERE encounter_id=?", (encounter_id,)
    ).fetchone()
    return row is not None


def _mark_enc_done(conn: sqlite3.Connection, encounter_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO enc_processed VALUES (?,?)",
        (encounter_id, datetime.utcnow().isoformat()),
    )
    conn.commit()


def _log_action(
    conn: sqlite3.Connection,
    encounter_id: str,
    action: str,
    concept_id: str,
    applied: bool,
    old_value: str | None,
    new_value: str | None,
    conf: float | None,
    reason: str | None,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO remediated VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            encounter_id, action, concept_id, int(applied),
            old_value, new_value, conf, reason, error,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()


_disputes_lock = threading.Lock()


def _log_dispute(path: Path, record: dict) -> None:
    with _disputes_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Load issues from audit DB
# ---------------------------------------------------------------------------


def load_issues(
    audit_db: Path,
    severity_filter: set[str] | None = None,
    encounter_filter: str | None = None,
) -> dict[str, dict[str, list]]:
    """Return {encounter_id: {overcoded, missing_critical, missing_high,
    wrong_assertion}} grouped from the audit SQLite DB."""
    conn = sqlite3.connect(str(audit_db))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    if encounter_filter:
        cur.execute(
            "SELECT encounter_id, result_json FROM encounters"
            " WHERE status='done' AND encounter_id=?",
            (encounter_filter,),
        )
    else:
        cur.execute(
            "SELECT encounter_id, result_json FROM encounters WHERE status='done'"
        )

    issues: dict[str, dict[str, list]] = {}
    for row in cur.fetchall():
        try:
            d = json.loads(row["result_json"])
        except Exception:
            continue

        enc_id = row["encounter_id"]
        overcoded = d.get("overcoded", [])
        wrong = [
            w for w in d.get("wrong_assertion", [])
            if w.get("current_assertion") != w.get("suggested_assertion")
        ]
        missing = []
        for m in d.get("missing", []):
            sev = m.get("severity", "low")
            if severity_filter and sev not in severity_filter:
                continue
            missing.append(m)

        if overcoded or missing or wrong:
            issues[enc_id] = {
                "overcoded": overcoded,
                "missing": missing,
                "wrong_assertion": wrong,
            }

    conn.close()
    return issues


# ---------------------------------------------------------------------------
# Sonnet verification
# ---------------------------------------------------------------------------


def _build_verify_message(
    text: str,
    date: str,
    coded: list[dict],
    proposed: list[dict],
) -> str:
    coded_lines = []
    for c in coded:
        if not c.get("concept_id"):
            continue
        coded_lines.append(
            f"  [{c['concept_id']}] {c.get('name','')} "
            f"({c.get('semantic_tag','')}) assertion={c.get('assertion','?')}"
        )
    coded_block = "\n".join(coded_lines) or "  (none)"

    changes_lines = []
    for i, p in enumerate(proposed):
        action = p["action"]
        if action == "delete":
            changes_lines.append(
                f"[{i}] DELETE '{p['name']}' ({p['concept_id']})"
                f" -- audit reason: {p['reason']}"
            )
        elif action == "add":
            changes_lines.append(
                f"[{i}] ADD '{p['search']}' as assertion={p['assertion']}"
                f" -- audit reason: {p['reason']}"
            )
        else:
            changes_lines.append(
                f"[{i}] UPDATE ASSERTION '{p['name']}' ({p['concept_id']})"
                f" {p['old_assertion']} -> {p['suggested_assertion']}"
                f" -- audit reason: {p['reason']}"
            )

    return (
        f"ENCOUNTER TEXT (date: {date}):\n{text}\n\n"
        f"CURRENT CODING ({len(coded_lines)} concepts):\n{coded_block}\n\n"
        f"PROPOSED CHANGES:\n" + "\n".join(changes_lines)
    )


def verify_with_sonnet(
    llm: Any,
    text: str,
    date: str,
    coded: list[dict],
    proposed: list[dict],
    max_attempts: int = 3,
) -> list[dict]:
    """Return list of verification dicts (index, agree, confidence, reason)."""
    msg = _build_verify_message(text, date, coded, proposed)
    for attempt in range(max_attempts):
        try:
            resp = llm.converse(
                system=_VERIFY_SYSTEM,
                messages=[{"role": "user", "content": msg}],
                max_tokens=2048,
                temperature=0.0,
            )
            parsed = _parse_verify_json(resp.text)
            return parsed.get("verifications", [])
        except Exception as exc:
            raw = str(exc)
            if "429" in raw or "ThrottlingException" in raw:
                wait = 30 * (attempt + 1)
                logger.warning("Throttled -- waiting %ds", wait)
                time.sleep(wait)
                continue
            if attempt == max_attempts - 1:
                logger.error("Sonnet failed after %d attempts: %s", max_attempts, exc)
                return []
            time.sleep(min(32, 2 ** (attempt + 1)))
    return []


# ---------------------------------------------------------------------------
# Apply fixes
# ---------------------------------------------------------------------------


def apply_delete(
    session: Any, encounter_id: str, concept_id: str, pg_client: PatientGraphClient
) -> bool:
    """Delete an overcoded DOCUMENTS relationship."""
    result = session.run(
        DELETE_OVERCODED_DOCUMENTS,
        encounter_id=encounter_id,
        concept_id=concept_id,
    ).single()
    if not result:
        return False
    if result.get("remaining_encounter_docs", 1) == 0:
        patient_row = session.run(
            GET_PATIENT_FOR_ENCOUNTER, encounter_id=encounter_id
        ).single()
        if patient_row:
            session.run(
                CLEANUP_PATIENT_SHORTCUT,
                patient_id=patient_row["patient_id"],
                concept_id=concept_id,
            )
    return True


def apply_add(
    session: Any,
    encounter_id: str,
    search_term: str,
    assertion: str,
    audit_reason: str,
    term_client: TerminologyClient,
) -> dict | None:
    """Resolve term via terminology API and add DOCUMENTS relationship.

    Tries the raw search term first, then stripped variants (removing SNOMED
    semantic tag suffixes that the audit LLM sometimes appends).
    Skips terms that are individual medication names.
    """
    if _is_medication_search(search_term):
        logger.debug("Skipping medication search term: %r", search_term)
        return None

    resolved = None
    for variant in _normalise_search_variants(search_term):
        try:
            r = term_client.resolve_one(variant)
            if r and r.concept_id:
                resolved = r
                if variant != search_term:
                    logger.debug("Resolved %r via stripped variant %r", search_term, variant)
                break
        except Exception as exc:
            logger.debug("Terminology resolve failed for %r: %s", variant, exc)

    if not resolved:
        return None

    concept_id = str(resolved.concept_id)
    name = resolved.term or search_term
    semantic_tag = resolved.semantic_tag or "other"
    label = _label_for_tag(semantic_tag)
    rel_type = _REL_BY_LABEL.get(label, "HAS_CONCEPT")
    query = build_add_documents_query(label, rel_type)

    session.run(
        query,
        encounter_id=encounter_id,
        concept_id=concept_id,
        name=name,
        semantic_tag=semantic_tag,
        assertion=assertion,
        evidence=audit_reason[:200],
        confidence=0.85,
    )
    return {"concept_id": concept_id, "name": name}


def apply_assertion_update(
    session: Any,
    encounter_id: str,
    concept_id: str,
    old_assertion: str,
    new_assertion: str,
) -> bool:
    """Update assertion on an existing DOCUMENTS relationship."""
    result = session.run(
        UPDATE_DOCUMENTS_ASSERTION,
        encounter_id=encounter_id,
        concept_id=concept_id,
        old_assertion=old_assertion,
        new_assertion=new_assertion,
    ).single()
    return bool(result and result.get("updated", 0) > 0)


# ---------------------------------------------------------------------------
# Per-encounter orchestration
# ---------------------------------------------------------------------------


def _build_proposed(issues: dict) -> list[dict]:
    """Flatten encounter issues into a flat list of proposed changes."""
    proposed = []
    for item in issues.get("overcoded", []):
        cid = str(item.get("conceptId") or "")
        if not cid or cid in _ALREADY_FIXED_CONCEPTS:
            continue
        proposed.append({
            "action": "delete",
            "concept_id": item["conceptId"],
            "name": item.get("name", ""),
            "reason": item.get("reason", ""),
        })
    for item in issues.get("missing", []):
        proposed.append({
            "action": "add",
            "search": item.get("snomed_search") or item.get("term", ""),
            "assertion": item.get("suggested_assertion", "present"),
            "reason": item.get("reason", ""),
        })
    for item in issues.get("wrong_assertion", []):
        cid = str(item.get("conceptId") or "")
        if not cid:
            continue
        proposed.append({
            "action": "update_assertion",
            "concept_id": item["conceptId"],
            "name": item.get("name", ""),
            "old_assertion": item.get("current_assertion", "present"),
            "suggested_assertion": item.get("suggested_assertion", "historical"),
            "reason": item.get("reason", ""),
        })
    return proposed


def remediate_encounter(
    encounter_id: str,
    issues: dict,
    llm: Any,
    pg_client: PatientGraphClient,
    term_client: TerminologyClient,
    rem_conn: sqlite3.Connection,
    dry_run: bool,
) -> dict[str, int]:
    """Process one encounter: verify + apply. Returns action counts."""
    counts = {"applied": 0, "disputed": 0, "skipped": 0, "error": 0}

    with pg_client.session() as session:
        row = session.run(
            GET_ENCOUNTER_FOR_REMEDIATION, encounter_id=encounter_id
        ).single()

    if not row or not row.get("text"):
        logger.warning("No text for encounter %s -- skipping", encounter_id)
        counts["skipped"] += 1
        return counts

    text = row["text"]
    date = row.get("date") or ""
    coded = [c for c in (row.get("coded") or []) if c.get("concept_id")]

    proposed = _build_proposed(issues)
    if not proposed:
        return counts

    verifications = verify_with_sonnet(llm, text, date, coded, proposed)
    verify_map = {v["index"]: v for v in verifications}

    with pg_client.session() as session:
        for i, change in enumerate(proposed):
            v = verify_map.get(i, {})
            agree = v.get("agree", False)
            conf = float(v.get("confidence", 0.0))
            reason = v.get("reason", "")
            action = change["action"]

            if not agree or conf < CONFIDENCE_THRESHOLD:
                counts["disputed"] += 1
                _log_dispute(DISPUTES_FILE, {
                    "encounter_id": encounter_id,
                    "index": i,
                    "change": change,
                    "agree": agree,
                    "confidence": conf,
                    "reason": reason,
                })
                _log_action(
                    rem_conn, encounter_id, action,
                    change.get("concept_id") or change.get("search", ""),
                    False, None, None, conf, reason,
                )
                continue

            applied = False
            old_val = new_val = None
            error = None

            if dry_run:
                logger.info(
                    "DRY-RUN %s enc=%s concept=%s conf=%.2f",
                    action, encounter_id[:8],
                    change.get("concept_id") or change.get("search"), conf,
                )
                applied = True
            else:
                try:
                    if action == "delete":
                        cid = change["concept_id"]
                        old_val = cid
                        applied = apply_delete(session, encounter_id, cid, pg_client)
                    elif action == "add":
                        result = apply_add(
                            session, encounter_id,
                            change["search"], change["assertion"],
                            change["reason"], term_client,
                        )
                        if result:
                            applied = True
                            new_val = result["concept_id"]
                        else:
                            counts["skipped"] += 1
                            _log_action(
                                rem_conn, encounter_id, action,
                                change["search"], False, None, None,
                                conf, "terminology_not_found",
                            )
                            continue
                    else:  # update_assertion
                        cid = change["concept_id"]
                        old_val = change["old_assertion"]
                        new_val = change["suggested_assertion"]
                        applied = apply_assertion_update(
                            session, encounter_id, cid, old_val, new_val
                        )
                except Exception as exc:
                    error = str(exc)[:300]
                    logger.error(
                        "Apply failed enc=%s action=%s: %s",
                        encounter_id[:8], action, exc,
                    )
                    counts["error"] += 1

            if applied:
                counts["applied"] += 1
            _log_action(
                rem_conn, encounter_id, action,
                change.get("concept_id") or change.get("search", ""),
                applied, old_val, new_val, conf, reason, error,
            )

    _mark_enc_done(rem_conn, encounter_id)
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Audit-driven encounter remediation")
    p.add_argument("--yes", action="store_true", help="Run for real (default is dry-run)")
    p.add_argument("--dry-run", action="store_true", help="Preview changes only")
    p.add_argument("--resume", action="store_true", help="Skip already-processed encounters")
    p.add_argument("--severity", default="critical,high", help="Comma-sep severities for missing items")
    p.add_argument("--encounter", help="Process a single encounter ID (for testing)")
    p.add_argument("--workers", type=int, default=5)
    p.add_argument("--limit", type=int, default=0, help="Max encounters to process (0=all)")
    p.add_argument(
        "--audit-db", default=str(AUDIT_DB),
        help="Path to audit SQLite DB",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    dry_run = args.dry_run or not args.yes

    if dry_run:
        logger.info("DRY-RUN mode -- no Neo4j writes will be made")
    else:
        logger.warning("LIVE mode -- changes will be written to Neo4j")

    severity_filter = set(args.severity.split(",")) if args.severity else None

    issues_map = load_issues(
        Path(args.audit_db),
        severity_filter=severity_filter,
        encounter_filter=args.encounter,
    )
    logger.info("Loaded %d encounters with issues", len(issues_map))

    # Initialise schema in main thread
    _init_remediation_db(REM_DB).close()
    DISPUTES_FILE.parent.mkdir(parents=True, exist_ok=True)

    if args.resume:
        _check_conn = sqlite3.connect(str(REM_DB))
        before = len(issues_map)
        issues_map = {
            enc: v for enc, v in issues_map.items()
            if not _is_enc_done(_check_conn, enc)
        }
        _check_conn.close()
        logger.info("Resume: skipped %d already-done, %d remaining", before - len(issues_map), len(issues_map))

    if args.limit:
        items = list(issues_map.items())[:args.limit]
        issues_map = dict(items)
        logger.info("Limited to %d encounters", len(issues_map))

    pg_client = PatientGraphClient()
    term_client = TerminologyClient(base_url=TERMINOLOGY_URL)
    llm = create_llm(provider="aws", tier="big")

    total_applied = total_disputed = total_skipped = total_error = 0
    done = 0
    total = len(issues_map)

    def _worker(enc_id: str, enc_issues: dict) -> dict:
        # Each thread gets its own SQLite connection (SQLite is not thread-safe)
        thread_conn = sqlite3.connect(str(REM_DB))
        try:
            return remediate_encounter(
                enc_id, enc_issues, llm, pg_client, term_client,
                thread_conn, dry_run,
            )
        finally:
            thread_conn.close()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_worker, enc, iss): enc
            for enc, iss in issues_map.items()
        }
        for future in as_completed(futures):
            enc = futures[future]
            try:
                counts = future.result()
                total_applied += counts["applied"]
                total_disputed += counts["disputed"]
                total_skipped += counts["skipped"]
                total_error += counts["error"]
            except Exception as exc:
                logger.error("Worker failed for %s: %s", enc[:8], exc)
                total_error += 1
            done += 1
            if done % 100 == 0 or done == total:
                logger.info(
                    "Progress %d/%d  applied=%d disputed=%d skip=%d err=%d",
                    done, total,
                    total_applied, total_disputed, total_skipped, total_error,
                )

    pg_client.close()

    print()
    print("=== REMEDIATION COMPLETE ===")
    print(f"  Encounters processed : {done:,}")
    print(f"  Changes applied      : {total_applied:,}")
    print(f"  Disputed (not applied): {total_disputed:,}")
    print(f"  Skipped (no concept) : {total_skipped:,}")
    print(f"  Errors               : {total_error:,}")
    print(f"  Dispute log          : {DISPUTES_FILE}")
    print(f"  Audit trail          : {REM_DB}")
    if not dry_run:
        print()
        print("Next step: re-run the audit to verify improvements.")
        print("  python scripts/investigations/audit_encounter_coding.py --yes --since 2024-01-01")


if __name__ == "__main__":
    main()
