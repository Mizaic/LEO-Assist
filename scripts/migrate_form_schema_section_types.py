"""Repair unrecognised ``section_type`` values on stored :FormSchema nodes.

Sections saved with a value outside the ``SectionType`` vocabulary -- the
Sherwood Gynaecology 2WW template stored ``"checkbox"`` on five of its seven
sections -- fall through ``_process_section_lines`` to a bare pass-through.
The deterministic checkbox control then does nothing at all, and unticked
2WW criteria reach the model as plain text.

The script is reversible and idempotent:

* It snapshots the whole node, including ``sections_json``, to a JSON file
  before it writes anything.
* It rewrites ``section_type`` only. Every other field on every section, and
  every other property on the node, is compared before and after and the
  write is abandoned if anything else moved.
* Running it twice changes nothing the second time.
* ``--restore <snapshot>`` puts the original ``sections_json`` back.

Connection details come from environment variables. There is no default
target: pass ``--env-prefix`` so the graph is always chosen deliberately.

Usage:
    python scripts/migrate_form_schema_section_types.py \\
        --env-prefix 98dd482b_ --fingerprint sfh-gynae-2ww-v1 --dry-run
    python scripts/migrate_form_schema_section_types.py \\
        --env-prefix 98dd482b_ --fingerprint sfh-gynae-2ww-v1 --apply
    python scripts/migrate_form_schema_section_types.py \\
        --env-prefix 98dd482b_ --restore snapshots/<file>.json

Atlas trace: DI-5C9CA57B
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

# Variable names here start with a digit, which a shell cannot export, so the
# file is read in-process rather than sourced.
load_dotenv(_REPO_ROOT / ".env", override=False)

from libs.pipeline.form_schema_section_types import (  # noqa: E402
    VALID_SECTION_TYPES,
    is_valid_section_type,
)

# The correct type for each section that was stored as "checkbox", decided
# against the real referral text in
# tests/fixtures/form_schema/sherwood_gynae_2ww_chunks_deid.json.
SECTION_TYPE_FIXES: dict[str, str] = {
    # "Ovary [ ] Cervix [X] ..." -- several sites may be ticked on one line.
    "section_a_cancer_type": "checkbox_multi",
    # "B1. ... | Yes [X] No [ ] |" -- one Yes/No pair per criterion row.
    "section_b_symptoms": "checkbox_yesno",
    # "New presentation with PMB ... | Yes [ ] |" -- Yes/No confirmations.
    "primary_care_pathway": "checkbox_yesno",
    # "... referred on an urgent basis? | [X] Yes [ ] No |" -- box first.
    "patient_awareness": "checkbox_yesno",
    # "1. Very Fit [X] | 2. Fit [ ] ..." -- one point on a scale.
    "section_e_performance": "scale",
}

READ_SCHEMA = """
MATCH (s:FormSchema {fingerprint: $fingerprint})
RETURN properties(s) AS props
"""

WRITE_SECTIONS = """
MATCH (s:FormSchema {fingerprint: $fingerprint})
SET s.sections_json = $sections_json,
    s.updated_at    = datetime()
RETURN s.schema_id AS schema_id
"""

SNAPSHOT_DIR = _REPO_ROOT / "scripts/snapshots"


class MigrationError(RuntimeError):
    """Raised when the graph is not in a state the script can safely change."""


def _driver(env_prefix: str):
    from neo4j import GraphDatabase

    uri = os.environ.get(f"{env_prefix}NEO4J_URI", "").strip()
    user = os.environ.get(f"{env_prefix}NEO4J_USER", "").strip()
    password = os.environ.get(f"{env_prefix}NEO4J_PASSWORD", "").strip()
    missing = [
        name
        for name, value in (
            (f"{env_prefix}NEO4J_URI", uri),
            (f"{env_prefix}NEO4J_USER", user),
            (f"{env_prefix}NEO4J_PASSWORD", password),
        )
        if not value
    ]
    if missing:
        raise MigrationError(f"Missing environment variables: {', '.join(missing)}")
    print(f"Graph: {uri}  user: {user}  password: {password[:4]}...")
    return GraphDatabase.driver(
        uri, auth=(user, password), max_transaction_retry_time=15
    )


def _read_props(driver, fingerprint: str) -> dict[str, Any]:
    with driver.session() as session:
        rows = list(session.run(READ_SCHEMA, fingerprint=fingerprint, timeout=30))
    if not rows:
        raise MigrationError(f"No :FormSchema found with fingerprint {fingerprint!r}")
    if len(rows) > 1:
        raise MigrationError(f"{len(rows)} :FormSchema nodes share {fingerprint!r}")
    return dict(rows[0]["props"])


def _planned_sections(
    sections: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[tuple[str, str, str]]]:
    """Return the rewritten sections and the list of changes."""
    planned: list[dict[str, Any]] = []
    changes: list[tuple[str, str, str]] = []
    for section in sections:
        section_id = str(section.get("section_id") or "")
        current = str(section.get("section_type") or "")
        if is_valid_section_type(current):
            planned.append(section)
            continue
        wanted = SECTION_TYPE_FIXES.get(section_id)
        if wanted is None:
            raise MigrationError(
                f"Section {section_id!r} holds unrecognised type {current!r} and "
                "this script has no mapping for it. Add one and re-run."
            )
        planned.append({**section, "section_type": wanted})
        changes.append((section_id, current, wanted))
    return planned, changes


def _assert_only_section_types_changed(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> None:
    """Abort unless the only difference is the ``section_type`` value."""
    if len(before) != len(after):
        raise MigrationError("Section count changed; refusing to write.")
    for old, new in zip(before, after):
        if set(old) != set(new):
            raise MigrationError(f"Field set changed on {old.get('section_id')!r}.")
        moved = {k for k in old if old[k] != new[k]}
        if moved - {"section_type"}:
            raise MigrationError(
                f"Fields other than section_type changed on "
                f"{old.get('section_id')!r}: {sorted(moved)}"
            )


def _write_snapshot(fingerprint: str, props: dict[str, Any]) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = SNAPSHOT_DIR / f"form_schema_{fingerprint}_{stamp}.json"
    payload = {
        "fingerprint": fingerprint,
        "captured_at": stamp,
        "properties": {k: str(v) for k, v in sorted(props.items())},
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="ascii")
    print(f"Snapshot written: {path}")
    return path


def _print_diff(changes: list[tuple[str, str, str]]) -> None:
    if not changes:
        print("No changes needed. Every section type is already recognised.")
        return
    width = max(len(c[0]) for c in changes)
    for section_id, current, wanted in changes:
        print(f"  {section_id:<{width}}  {current}  ->  {wanted}")


def _report_unchanged_properties(before: dict[str, Any], after: dict[str, Any]) -> None:
    moved = {
        k for k in set(before) | set(after) if str(before.get(k)) != str(after.get(k))
    }
    expected = {"sections_json", "updated_at"}
    print(f"Node properties that changed: {sorted(moved)}")
    unexpected = moved - expected
    if unexpected:
        raise MigrationError(f"Unexpected property changes: {sorted(unexpected)}")


def migrate(driver, fingerprint: str, apply_changes: bool) -> int:
    props = _read_props(driver, fingerprint)
    sections = json.loads(props.get("sections_json") or "[]")
    planned, changes = _planned_sections(sections)
    _assert_only_section_types_changed(sections, planned)

    print(f"\nSchema {fingerprint!r} has {len(sections)} sections.")
    print(f"Recognised vocabulary: {', '.join(sorted(VALID_SECTION_TYPES))}\n")
    _print_diff(changes)

    if not changes:
        return 0
    if not apply_changes:
        print("\nDry run. Nothing written. Re-run with --apply to write.")
        return 0

    _write_snapshot(fingerprint, props)
    sections_json = json.dumps(planned, ensure_ascii=True)
    with driver.session() as session:
        rows = list(
            session.run(
                WRITE_SECTIONS,
                fingerprint=fingerprint,
                sections_json=sections_json,
                timeout=30,
            )
        )
    if not rows:
        raise MigrationError("Write matched no node.")
    print(f"Updated schema_id {rows[0]['schema_id']}.")

    after = _read_props(driver, fingerprint)
    _report_unchanged_properties(props, after)
    _assert_only_section_types_changed(sections, json.loads(after["sections_json"]))
    print("Verified: only section_type values changed.")
    return len(changes)


def restore(driver, snapshot_path: Path) -> None:
    payload = json.loads(snapshot_path.read_text(encoding="ascii"))
    fingerprint = payload["fingerprint"]
    sections_json = payload["properties"]["sections_json"]
    with driver.session() as session:
        rows = list(
            session.run(
                WRITE_SECTIONS,
                fingerprint=fingerprint,
                sections_json=sections_json,
                timeout=30,
            )
        )
    if not rows:
        raise MigrationError("Restore matched no node.")
    print(f"Restored {fingerprint} from {snapshot_path}.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-prefix",
        required=True,
        help="Prefix for NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD, e.g. 98dd482b_",
    )
    parser.add_argument("--fingerprint", default="", help="FormSchema.fingerprint")
    parser.add_argument("--dry-run", action="store_true", help="Print the diff only")
    parser.add_argument("--apply", action="store_true", help="Write the changes")
    parser.add_argument("--restore", default="", help="Snapshot file to restore")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.apply and args.dry_run:
        raise SystemExit("Choose --dry-run or --apply, not both.")
    if not args.restore and not args.fingerprint:
        raise SystemExit("--fingerprint is required unless --restore is used.")
    driver = _driver(args.env_prefix)
    try:
        if args.restore:
            restore(driver, Path(args.restore))
        else:
            migrate(driver, args.fingerprint, apply_changes=args.apply)
    except MigrationError as exc:
        raise SystemExit(f"Stopped: {exc}") from exc
    finally:
        driver.close()


if __name__ == "__main__":
    main()
