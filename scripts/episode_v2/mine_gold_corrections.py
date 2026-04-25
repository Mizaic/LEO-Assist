"""Mine v1.1 candidate rulebooks from the sign-off audit trail.

Atlas trace:
  DI: DI-D983C6EE (correction-driven rulebook retrain loop)

Reads ``EpisodeManualAttach`` / ``EpisodeManualDetach`` audit events
for the three gold-sign-off patients (9990001002, 9990001004,
9990001005), normalises them into ``CorrectionEvent`` rows, runs
the pattern miner per site, and writes a v1.1 candidate rulebook
to ``.local/rulebook_candidates/`` for each site that yielded a
signal. The candidates are REGISTERED only -- promotion to
champion still requires the gold-patient VT pass through the
registry CLI.

Usage::

    python -m scripts.episode_v2.mine_gold_corrections
    python -m scripts.episode_v2.mine_gold_corrections --apply-to-dry-run

When ``--apply-to-dry-run`` is passed the script also installs the
candidate rulebooks into the current bundle and re-runs the dry-run
so we can compare AUTO episode membership with gold in one command.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from libs.episode_detector.loader import (
    DEFAULTS_DIR,
    load_default_bundle,
    load_rulebook,
    override_sites,
    set_current_bundle,
)
from libs.episode_detector.pattern_miner import MinerResult, propose_candidate
from libs.episode_detector.rulebook import SiteRulebook
from libs.episode_learning.correction_capture import (
    CorrectionEvent,
    capture_corrections_from_audit,
)
from libs.testing.synthetic_patient_ids import (
    GOLD_BREAST_CLOSED_BENIGN,
    GOLD_MULTI_PATHWAY,
    GOLD_PROSTATE_COMPLETED,
)

logger = logging.getLogger(__name__)

GOLD_PATIENTS: tuple[str, ...] = (
    GOLD_BREAST_CLOSED_BENIGN,
    GOLD_MULTI_PATHWAY,
    GOLD_PROSTATE_COMPLETED,
)
OUTPUT_DIR = Path(".local/rulebook_candidates")

# Map the sign-off audit's free-text suspected_site to the canonical
# rulebook site_key. Reviewers see the user-facing label ("Upper GI",
# "Prostate") but rulebooks are keyed on the strict identifier.
_SITE_KEY_ALIASES: dict[str, str] = {
    "prostate": "prostate_urological",
    "prostate cancer": "prostate_urological",
    "urology": "prostate_urological",
    "upper gi": "upper_gi",
    "upper_gi": "upper_gi",
    "lower gi": "lower_gi",
    "lower_gi": "lower_gi",
    "head and neck": "head_neck",
    "head_neck": "head_neck",
    "brain and cns": "brain_cns",
    "brain_cns": "brain_cns",
}


def _canonical_site(raw: str | None) -> str:
    """Map a free-text site label to the rulebook canonical site_key."""
    value = (raw or "").strip().lower()
    if not value:
        return "unknown"
    return _SITE_KEY_ALIASES.get(value, value)


_ENCOUNTER_ID_RE = re.compile(
    r"encounter=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)


def _encounter_ids_from_notes(notes: str | None) -> list[str]:
    """Extract encounter UUIDs from the audit note string."""
    if not notes:
        return []
    return [m.group(1).lower() for m in _ENCOUNTER_ID_RE.finditer(notes)]


AUDIT_CYPHER = """
MATCH (a:AuditEvent)
WHERE a.patient_id IN $patient_ids
  AND a.type IN ['EpisodeManualAttach', 'EpisodeManualDetach',
                 'episode_manual_attach', 'episode_manual_detach']
RETURN
  a.id AS id,
  a.type AS type,
  a.correction_target AS correction_target,
  a.episode_id AS episode_id,
  a.patient_id AS patient_id,
  a.actor_role AS actor_role,
  a.before_json AS before_json,
  a.after_json AS after_json,
  a.created_at_iso AS created_at_iso,
  a.notes AS notes,
  a.subtype AS subtype
"""

# Pull every SNOMED concept attached to the encounter. In the
# patient graph, encounters link to coded entities via
# ``:DOCUMENTS`` (direct observations / procedures / situations) and
# via ``:HAS_DOCUMENT -> Document -> :CONTAINS`` (free-text coded by
# NER). Concept IDs live on the camelCase ``conceptId`` field.
ENCOUNTER_CODES_CYPHER = """
UNWIND $encounter_ids AS eid
MATCH (e:Encounter {id: eid})
OPTIONAL MATCH (e)-[:DOCUMENTS]->(c1)
OPTIONAL MATCH (e)-[:HAS_DOCUMENT]->(:Document)-[:CONTAINS]->(c2)
WITH eid,
     collect(DISTINCT c1.conceptId) AS direct_ids,
     collect(DISTINCT c2.conceptId) AS doc_ids
RETURN eid AS encounter_id,
       [c IN direct_ids + doc_ids WHERE c IS NOT NULL] AS concept_ids
"""

# Look up each episode's suspected_site so we can tag the audit event.
# :EpisodeOfCare uses the ``episode_id`` property as its stable key
# (the ``id`` property is unused / often null).
EPISODE_SITE_CYPHER = """
UNWIND $episode_ids AS eid
MATCH (e:EpisodeOfCare {episode_id: eid})
RETURN e.episode_id AS episode_id,
       e.suspected_site AS suspected_site,
       e.site_key AS site_key,
       e.cancer_type AS cancer_type
"""


def _load_baseline_bundle() -> dict[str, SiteRulebook]:
    """Build the latest champion baseline (v1 where authored, v0 everywhere
    else). The miner starts from this and proposes additions on top.
    """
    bundle = load_default_bundle()
    v1_overrides: dict[str, SiteRulebook] = {}
    for path in sorted(Path(DEFAULTS_DIR).glob("*.v1.json")):
        rb = load_rulebook(path)
        v1_overrides[rb.site_key] = rb
    if v1_overrides:
        bundle = override_sites(bundle, v1_overrides)
    return dict(bundle.sites)


def _pull_audit_rows_and_codes() -> (
    tuple[list[dict[str, Any]], dict[str, set[str]], dict[str, str]]
):
    """Fetch audit events plus two enrichment dictionaries.

    Returns ``(audit_rows, encounter_id -> snomed_codes,
    episode_id -> raw_site_label)``. The site label is whatever the
    episode carries (for example ``"Breast"`` or ``"Prostate"``); it
    is normalised to the canonical rulebook key downstream.
    """
    from libs.keyvault.loader import load_keyvault_secrets
    from libs.neo4j_client.client import PatientGraphClient

    load_keyvault_secrets()
    client = PatientGraphClient()
    try:
        raw_audit = client.run(AUDIT_CYPHER, patient_ids=list(GOLD_PATIENTS))
        audit_rows = [_to_dict(r) for r in raw_audit or []]

        encounter_ids: set[str] = set()
        episode_ids: set[str] = set()
        for row in audit_rows:
            encounter_ids.update(_encounter_ids_from_notes(row.get("notes")))
            if row.get("episode_id"):
                episode_ids.add(str(row["episode_id"]))

        encounter_codes: dict[str, set[str]] = {}
        if encounter_ids:
            raw_codes = client.run(
                ENCOUNTER_CODES_CYPHER,
                encounter_ids=list(encounter_ids),
            )
            for r in raw_codes or []:
                row = _to_dict(r)
                eid = str(row.get("encounter_id") or "")
                concept_ids = row.get("concept_ids") or []
                encounter_codes[eid] = {
                    str(c) for c in concept_ids if c and str(c).isdigit()
                }

        episode_sites: dict[str, str] = {}
        if episode_ids:
            raw_sites = client.run(
                EPISODE_SITE_CYPHER,
                episode_ids=list(episode_ids),
            )
            for r in raw_sites or []:
                row = _to_dict(r)
                eid = str(row.get("episode_id") or "")
                label = (
                    row.get("site_key")
                    or row.get("suspected_site")
                    or row.get("cancer_type")
                    or ""
                )
                if eid and label:
                    episode_sites[eid] = str(label)
    finally:
        client.close()
    return audit_rows, encounter_codes, episode_sites


def _to_dict(record: Any) -> dict[str, Any]:
    if hasattr(record, "data"):
        return dict(record.data())
    if isinstance(record, dict):
        return dict(record)
    return dict(record)


def _enrich_audit_rows(
    rows: list[dict[str, Any]],
    encounter_codes: dict[str, set[str]],
    episode_sites: dict[str, str],
) -> list[dict[str, Any]]:
    """Stamp each attach/detach row with the SNOMED codes of the
    encounter it references, so the miner sees concrete codes to
    absorb. Also injects a ``correction_target`` of
    ``coding_decision`` when the target is unset -- this is what the
    miner needs to treat the row as actionable.
    """
    enriched: list[dict[str, Any]] = []
    for row in rows:
        encs = _encounter_ids_from_notes(row.get("notes"))
        codes: set[str] = set()
        for eid in encs:
            codes.update(encounter_codes.get(eid, set()))
        event_type = (row.get("type") or "").strip().lower()
        patched = dict(row)
        # Always force a non-null correction_target so the miner's
        # code-target gate lets the row through. Sign-off flows never
        # set the legacy correction_target field; we know by
        # construction these are coding-decision corrections.
        patched["correction_target"] = row.get("correction_target") or "coding_decision"
        # Build after_json from the enriched codes so the miner sees
        # a concrete code snapshot. For attach: put codes in 'after'.
        # For detach: put codes in 'before' so the miner treats them
        # as removed (-> cross_site_guard).
        after_json = _safe_parse_json(row.get("after_json"))
        before_json = _safe_parse_json(row.get("before_json"))
        if "attach" in event_type:
            after_json.setdefault("encounter_codes", sorted(codes))
        elif "detach" in event_type:
            before_json.setdefault("encounter_codes", sorted(codes))
        # Stamp the episode's suspected_site onto the snapshot so
        # correction_capture can pick up a site_key instead of
        # falling back to "unknown".
        site_label = episode_sites.get(str(row.get("episode_id") or ""))
        if site_label:
            after_json.setdefault("suspected_site", site_label)
            before_json.setdefault("suspected_site", site_label)
        patched["after_json"] = json.dumps(after_json)
        patched["before_json"] = json.dumps(before_json)
        enriched.append(patched)
    return enriched


def _safe_parse_json(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(value)
        return dict(parsed) if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _normalise_site(event: CorrectionEvent) -> CorrectionEvent:
    """Apply the site-key alias table to a captured event."""
    site = _canonical_site(event.site_key)
    if site == event.site_key:
        return event
    return replace(event, site_key=site)


def _group_by_site(events: list[CorrectionEvent]) -> dict[str, list[CorrectionEvent]]:
    grouped: dict[str, list[CorrectionEvent]] = {}
    for event in events:
        grouped.setdefault(event.site_key, []).append(event)
    return grouped


def _write_candidate(candidate: SiteRulebook, *, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{candidate.site_key}.v1_1_mined.json"
    path.write_text(candidate.to_json(indent=2) + "\n", encoding="utf-8")
    return path


def _print_result(result: MinerResult, output_path: Path | None) -> None:
    print(f"  site={result.site_key}")
    print(f"    events considered : {result.events_considered}")
    print(f"    events w/ signal  : {result.events_with_signal}")
    if result.added_suspected:
        print(f"    + suspected_snomed: {list(result.added_suspected)}")
    if result.added_confirmed:
        print(f"    + confirmed_snomed: {list(result.added_confirmed)}")
    if result.added_referral:
        print(f"    + referral_snomed : {list(result.added_referral)}")
    if result.added_cross_site_guard:
        print(f"    + cross_site_guard: {list(result.added_cross_site_guard)}")
    if output_path is not None:
        print(f"    -> wrote candidate: {output_path}")
    if result.reason:
        print(f"    reason: {result.reason}")


def _mine(apply_candidates: bool, output_dir: Path) -> dict[str, SiteRulebook]:
    baseline = _load_baseline_bundle()
    audit_rows, encounter_codes, episode_sites = _pull_audit_rows_and_codes()
    print(f"Audit rows pulled: {len(audit_rows)}")
    print(f"Encounters with SNOMEDs: {len(encounter_codes)}")
    print(f"Episodes with site tag : {len(episode_sites)}")
    enriched_rows = _enrich_audit_rows(audit_rows, encounter_codes, episode_sites)
    raw_events = capture_corrections_from_audit(enriched_rows)
    events = [_normalise_site(e) for e in raw_events]
    print(f"Normalised CorrectionEvents: {len(events)}")
    grouped = _group_by_site(events)
    print(f"Sites seen: {sorted(grouped.keys())}")

    raw_candidates: dict[str, SiteRulebook] = {}
    raw_results: dict[str, MinerResult] = {}
    for site, site_events in sorted(grouped.items()):
        base = baseline.get(site)
        if base is None:
            print(
                f"  site={site}: no baseline rulebook; skipping "
                f"({len(site_events)} events left on the floor)"
            )
            continue
        next_version = f"{base.rulebook_version}+mined.gold3"
        result = propose_candidate(
            site_events,
            baseline=base,
            next_version=next_version,
            site_key=site,
        )
        raw_results[site] = result
        if result.candidate_rulebook is not None:
            raw_candidates[site] = result.candidate_rulebook

    # Post-process: when a code appears in more than one site's
    # "added suspected" list, it is an everyday/common SNOMED (GP
    # visit, assessment) rather than a site-specific anchor. Strip
    # those out so the v1.1 candidates do not over-fire activation
    # from a handful of gold patients. Similarly, a code that lands
    # in both ``added_suspected`` and ``added_cross_site_guard`` for
    # the same site is a direct contradiction; attach-evidence wins.
    candidates = _post_process_candidates(raw_candidates, raw_results, baseline)
    for site, rb in sorted(candidates.items()):
        output_path = _write_candidate(rb, output_dir=output_dir)
        _print_result(raw_results[site], output_path)

    if apply_candidates and candidates:
        print()
        print(f"Installing {len(candidates)} mined candidate(s) into bundle...")
        set_current_bundle(
            override_sites(load_default_bundle(), {**baseline, **candidates})
        )
    return candidates


def _post_process_candidates(
    raw: dict[str, SiteRulebook],
    results: dict[str, MinerResult],
    baseline: dict[str, SiteRulebook],
) -> dict[str, SiteRulebook]:
    """Filter noise from the raw miner output.

    Two rules:

    1. A code proposed as ``suspected_snomed`` for more than one site
       is an everyday SNOMED (GP visit, assessment) and gets dropped
       from every site's additions. Baseline codes are untouched.
    2. Within one site, a code cannot be both a new suspected anchor
       and a new cross-site guard -- attach evidence wins.
    """
    from collections import Counter
    from dataclasses import replace

    suspected_counts: Counter[str] = Counter()
    for res in results.values():
        for code in res.added_suspected:
            suspected_counts[code] += 1
    common_codes = {c for c, n in suspected_counts.items() if n >= 2}

    cleaned: dict[str, SiteRulebook] = {}
    for site, rb in raw.items():
        res = results[site]
        base = baseline[site]
        new_suspected = {c for c in res.added_suspected if c not in common_codes}
        new_guards = {
            c
            for c in res.added_cross_site_guard
            if c not in common_codes and c not in new_suspected
        }
        new_referral = set(res.added_referral)
        new_confirmed = set(res.added_confirmed)

        if not (new_suspected or new_guards or new_referral or new_confirmed):
            continue

        anchors = replace(
            base.anchors,
            suspected_snomed=_merge_codes(base.anchors.suspected_snomed, new_suspected),
            referral_snomed=_merge_codes(base.anchors.referral_snomed, new_referral),
            confirmed_snomed=_merge_codes(base.anchors.confirmed_snomed, new_confirmed),
        )
        guards = _merge_codes(base.cross_site_guard, new_guards)
        cleaned[site] = replace(
            base,
            rulebook_version=rb.rulebook_version,
            anchors=anchors,
            cross_site_guard=guards,
        )
    print(
        f"  Post-processing: dropped {len(common_codes)} multi-site "
        f"suspected codes as everyday noise."
    )
    return cleaned


def _merge_codes(existing: tuple[str, ...], additions: set[str]) -> tuple[str, ...]:
    """Order-preserving dedupe of a tuple-plus-additions."""
    seen = set(existing)
    out = list(existing)
    for code in sorted(additions):
        if code not in seen:
            out.append(code)
            seen.add(code)
    return tuple(out)


async def _run_dry_run(patient_id: str) -> None:
    from scripts.episode_v2.dry_run_patient import dry_run

    print()
    print("=" * 78)
    print(f"Re-dry-run with mined candidates applied -- patient {patient_id}")
    print("=" * 78)
    # We already installed the bundle above, so pass --rulebook-version v0
    # to avoid the dry_run helper overwriting it.
    await dry_run(patient_id, rulebook_version="v0")


def _cli_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR),
        help="Where to write the v1.1 candidate rulebook JSON files.",
    )
    parser.add_argument(
        "--apply-to-dry-run",
        action="store_true",
        help=(
            "After mining, install the candidates into the process "
            "bundle and re-run the dry-run for the three gold patients."
        ),
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    candidates = _mine(
        apply_candidates=bool(args.apply_to_dry_run),
        output_dir=Path(args.output_dir),
    )

    print()
    print(
        json.dumps(
            {
                "candidates_emitted": sorted(candidates.keys()),
                "output_dir": str(Path(args.output_dir).resolve()),
            },
            indent=2,
        )
    )

    if args.apply_to_dry_run and candidates:
        for pid in GOLD_PATIENTS:
            asyncio.run(_run_dry_run(pid))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
