"""Stage 1 backfill: write deterministic source_row_text matches.

For every AppropriatenessRule leaf missing `source_row_text` where the
shared matcher (scripts/investigations/_rule_text_match.py) finds a real
verbatim span in the rule's OWN linked recommendation text, writes that
exact substring into `source_row_text`.

Safety:
  - Defaults to a dry run. Pass --apply to write.
  - Backs up every touched rule's current logicJson to
    scripts/investigations/_backfill_backups/ before the first write.
  - Before each write, diffs old vs new tree with
    diff_ignoring_source_row_text() -- if anything other than
    source_row_text changed, the rule is skipped and reported as unsafe.
  - Records a GuidanceAuditEvent (action=backfill_source_row_text_stage1)
    on every rule actually written.
  - Never touches rule.status / reviewedAt / reviewedBy / updatedAt.

Run from repo root:
    python scripts/investigations/_backfill_source_row_text_apply.py            # dry run
    python scripts/investigations/_backfill_source_row_text_apply.py --apply    # writes
    python scripts/investigations/_backfill_source_row_text_apply.py --apply --guideline NG12
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_keyvault_secrets()

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

BACKUP_DIR = ROOT / "scripts" / "investigations" / "_backfill_backups"
ACTOR = "backfill_script:stage1_deterministic"


@dataclass
class RuleOutcome:
    rule_id: str
    guideline_id: str
    leaves_filled: int = 0
    unsafe_reasons: list[str] = field(default_factory=list)


def fill_rule(
    logic_json: str, text: str | None
) -> tuple[dict[str, Any], int]:
    """Returns (new_tree, count_filled). Mutates a deep copy only."""
    tree = json.loads(logic_json)
    new_tree = copy.deepcopy(tree)
    filled = 0
    for leaf in walk_leaves(new_tree):
        if leaf.get("source_row_text"):
            continue
        _, candidates = leaf_candidates(leaf)
        span = first_matching_span(text, candidates)
        if span:
            leaf["source_row_text"] = span.matched_text
            filled += 1
    return new_tree, filled


def process_rule(row: dict[str, Any], apply: bool, driver: Any) -> RuleOutcome | None:
    rule_id = row["rule_id"]
    guideline_id = row["guideline_id"]
    logic_json = row.get("logic_json")
    if not logic_json:
        return None

    try:
        old_tree = json.loads(logic_json)
        new_tree, filled = fill_rule(logic_json, row.get("recommendation_text"))
    except (json.JSONDecodeError, TypeError):
        return None
    if filled == 0:
        return None

    outcome = RuleOutcome(rule_id=rule_id, guideline_id=guideline_id, leaves_filled=filled)
    unsafe = diff_ignoring_source_row_text(old_tree, new_tree)
    if unsafe:
        outcome.unsafe_reasons = unsafe
        return outcome

    if apply:
        write_logic_json(
            driver,
            rule_id,
            new_tree,
            action="backfill_source_row_text_stage1",
            actor=ACTOR,
            reason=f"Deterministic text match filled {filled} leaf(ves) source_row_text.",
        )
    return outcome


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

        outcomes = [o for row in rows if (o := process_rule(row, args.apply, driver)) is not None]
    finally:
        driver.close()

    safe = [o for o in outcomes if not o.unsafe_reasons]
    unsafe = [o for o in outcomes if o.unsafe_reasons]
    total_filled = sum(o.leaves_filled for o in safe)

    print("=" * 72)
    print(f"STAGE 1 BACKFILL -- {'APPLIED' if args.apply else 'DRY RUN'}")
    print("=" * 72)
    print(f"Rules with >=1 fillable leaf: {len(outcomes)}")
    print(f"  safe to write (only source_row_text changed): {len(safe)} rules, {total_filled} leaves")
    print(f"  BLOCKED by safety diff (skipped, not written): {len(unsafe)} rules")
    for o in unsafe:
        print(f"    [{o.guideline_id}] {o.rule_id}")
        for reason in o.unsafe_reasons[:3]:
            print(f"      - {reason}")


if __name__ == "__main__":
    main()
