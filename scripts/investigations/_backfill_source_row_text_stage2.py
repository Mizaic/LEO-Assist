"""Stage 2 backfill: LLM-assisted source_row_text for the Stage-1 residual.

For every leaf Stage 1 (pure deterministic text matching) could not anchor,
asks a small-tier LLM for the shortest verbatim phrase in the rule's OWN
recommendation text that plausibly corresponds to the SNOMED term.

Safety -- the LLM is a SUGGESTER ONLY, never a writer:
  - Its candidate string is thrown away unless the shared deterministic
    matcher (scripts/investigations/_rule_text_match.py) independently
    finds that candidate as a real substring/token-overlap span inside
    the rule's OWN recommendation text.
  - Nothing is ever written from the LLM's own wording -- the ACTUAL
    substring of the guideline text (from the verified span) is what
    gets stored, guaranteeing verbatim provenance even if the model
    mis-transcribes case, punctuation, or spelling.
  - Cross-referenced / table-derived leaves (the term genuinely isn't in
    this rule's own text) correctly stay unmatched -- the LLM may guess,
    but the verifier will reject it, same as Stage 1.
  - Defaults to a dry run. Pass --apply to write. Same backup +
    diff-safety-check + GuidanceAuditEvent trail as Stage 1
    (see _backfill_source_row_text_apply.py, _rule_kg_io.py).

Run from repo root:
    python scripts/investigations/_backfill_source_row_text_stage2.py            # dry run
    python scripts/investigations/_backfill_source_row_text_stage2.py --apply    # writes
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_keyvault_secrets()

from libs.llm_client.factory import create_llm  # noqa: E402
from libs.llm_client.prompt_safety import (  # noqa: E402
    INJECTION_GUARD,
    cap_llm_response,
    redact_for_log,
    sanitise_for_prompt,
)
from scripts.investigations._backfill_source_row_text_apply import BACKUP_DIR  # noqa: E402
from scripts.investigations._rule_kg_io import (  # noqa: E402
    backup_rules,
    connect,
    diff_ignoring_source_row_text,
    fetch_rule_rows,
    write_logic_json,
)
from scripts.investigations._rule_text_match import (  # noqa: E402
    first_matching_span,
    leaf_candidates,
    walk_leaves,
)

ACTOR = "backfill_script:stage2_llm_assisted"
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

_SYSTEM = INJECTION_GUARD + (
    "You help backfill provenance metadata for a UK clinical guideline "
    "rule-authoring tool. You will be given one guideline sentence and one "
    "SNOMED CT clinical term that a coder attached to a rule built from "
    "that sentence.\n\n"
    "Find the SHORTEST phrase inside the sentence that this term is a "
    "plain synonym or paraphrase of (e.g. 'dyspnoea' is a synonym of "
    "'shortness of breath').\n\n"
    "RULES:\n"
    "1. The candidate MUST be copied character-for-character from the "
    "sentence -- never invent, correct, or reword it.\n"
    "2. Only propose a candidate for a genuine synonym/paraphrase "
    "relationship, not a loosely related concept.\n"
    "3. If the sentence has no such phrase (the term likely came from a "
    "different sentence, a table, or a differential diagnosis list), "
    "set candidate to null. Returning null is the correct, safe answer "
    "when unsure.\n"
    "4. Reply with JSON only: "
    '{"candidate": "<verbatim phrase or null>", "confidence": '
    '"high" | "medium" | "low", "reason": "one short sentence"}\n'
)


@dataclass
class Stage2Result:
    rule_id: str
    guideline_id: str
    kind: str
    label: str
    llm_candidate: str | None
    llm_confidence: str
    llm_reason: str
    verified_text: str | None


def _parse_json(text: str) -> dict:
    text = cap_llm_response(text, max_chars=1000).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def ask_llm_for_candidate(label: str, text: str) -> tuple[str | None, str, str]:
    user_msg = json.dumps(
        {
            "guideline_sentence": sanitise_for_prompt(text, max_chars=2000),
            "snomed_term": sanitise_for_prompt(label, max_chars=200),
        }
    )
    try:
        client = create_llm(provider="aws", tier="small")
        response = client.converse(
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            temperature=0.0,
            max_tokens=300,
            agent_task="backfill_source_row_text_stage2",
        )
    except Exception as exc:  # noqa: BLE001 -- log and treat as "no candidate"
        print(f"  LLM call failed for {redact_for_log(label)}: {exc}")
        return None, "low", "LLM call failed"

    parsed = _parse_json(response.text or "")
    candidate = parsed.get("candidate")
    if not isinstance(candidate, str) or not candidate.strip():
        candidate = None
    confidence = parsed.get("confidence") if isinstance(parsed.get("confidence"), str) else "low"
    reason = parsed.get("reason") if isinstance(parsed.get("reason"), str) else ""
    return candidate, confidence, reason


def find_unmatched_leaves(rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Returns [(row, leaf_dict)] for every leaf Stage 1 could not anchor."""
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for row in rows:
        if not row.get("logic_json"):
            continue
        try:
            tree = json.loads(row["logic_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        text = row.get("recommendation_text")
        for leaf in walk_leaves(tree):
            if leaf.get("source_row_text"):
                continue
            _, candidates = leaf_candidates(leaf)
            if first_matching_span(text, candidates) is None:
                out.append((row, leaf))
    return out


def run_stage2(rows: list[dict[str, Any]]) -> list[Stage2Result]:
    pending = find_unmatched_leaves(rows)
    print(f"Stage 1 left {len(pending)} unmatched leaves. Asking small-tier LLM for each...\n")
    results: list[Stage2Result] = []
    for row, leaf in pending:
        text = row.get("recommendation_text") or ""
        label, _ = leaf_candidates(leaf)
        kind = (leaf.get("kind") or "").upper()
        candidate, confidence, reason = ask_llm_for_candidate(label, text)
        span = first_matching_span(text, [candidate]) if candidate else None
        verified = span.matched_text if span else None
        tag = "VERIFIED" if verified else "rejected"
        print(f"  [{tag}] {row['guideline_id']} {kind:12s} {label!r} -> {candidate!r} ({confidence})")
        results.append(
            Stage2Result(
                rule_id=row["rule_id"], guideline_id=row["guideline_id"], kind=kind,
                label=label, llm_candidate=candidate, llm_confidence=confidence,
                llm_reason=reason, verified_text=verified,
            )
        )
    return results


def apply_verified(rows: list[dict[str, Any]], results: list[Stage2Result], driver: Any, apply: bool) -> int:
    verified_by_rule: dict[str, dict[str, str]] = {}
    for r in results:
        if r.verified_text:
            verified_by_rule.setdefault(r.rule_id, {})[r.label] = r.verified_text

    written = 0
    for row in rows:
        rule_id = row["rule_id"]
        if rule_id not in verified_by_rule:
            continue
        old_tree = json.loads(row["logic_json"])
        new_tree = copy.deepcopy(old_tree)
        filled = 0
        for leaf in walk_leaves(new_tree):
            if leaf.get("source_row_text"):
                continue
            label, _ = leaf_candidates(leaf)
            match = verified_by_rule[rule_id].get(label)
            if match:
                leaf["source_row_text"] = match
                filled += 1
        if filled == 0:
            continue
        unsafe = diff_ignoring_source_row_text(old_tree, new_tree)
        if unsafe:
            print(f"  BLOCKED (unsafe diff) {rule_id}: {unsafe[:2]}")
            continue
        written += filled
        if apply:
            write_logic_json(
                driver, rule_id, new_tree,
                action="backfill_source_row_text_stage2",
                actor=ACTOR,
                reason=f"LLM-suggested, deterministically-verified match filled {filled} leaf(ves).",
            )
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guideline", default=None, help="Restrict to one guideline id, e.g. NG12")
    parser.add_argument("--apply", action="store_true", help="Actually write. Omit for a dry run.")
    args = parser.parse_args()

    driver = connect()
    try:
        rows = fetch_rule_rows(driver, args.guideline)
        print(f"Fetched {len(rows)} rules from Neo4j.")
        if args.apply:
            backup_path = backup_rules(rows, BACKUP_DIR)
            print(f"Backed up current logicJson for {len(rows)} rules to {backup_path}\n")
        else:
            print("DRY RUN -- no writes. Pass --apply to write.\n")

        results = run_stage2(rows)
        written = apply_verified(rows, results, driver, args.apply)
    finally:
        driver.close()

    verified_n = sum(1 for r in results if r.verified_text)
    print()
    print("=" * 72)
    print(f"STAGE 2 LLM-ASSISTED BACKFILL -- {'APPLIED' if args.apply else 'DRY RUN'}")
    print("=" * 72)
    print(f"Leaves sent to LLM:            {len(results)}")
    print(f"LLM candidate verified in text: {verified_n}")
    print(f"Leaves written:                 {written}")
    print(f"Still needs human review:      {len(results) - verified_n}")


if __name__ == "__main__":
    main()
