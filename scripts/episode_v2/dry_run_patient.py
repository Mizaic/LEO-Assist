"""Dry-run the Episode Detector v2 against a real patient in the live graph.

Atlas trace:
  DI: DI-8A5FCF4F (Defence-in-depth episode detector)

Wraps the real PatientGraphClient so the runner can read the live
graph but every WRITE Cypher (MERGE / CREATE / SET / DELETE) is
intercepted and turned into a no-op log line. Output is printed to
stdout: detected episodes (with site, dates, tier, encounter count,
review reasons), the suppressed write payload (so we can see what
would be persisted), and the coverage report.

Usage::

    python -m scripts.episode_v2.dry_run_patient --patient-id 9990001004
    python -m scripts.episode_v2.dry_run_patient --patient-id 9990001005
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _install_text_only_timeline() -> None:
    """Monkey-patch the runner's ``load_timeline`` import so that every
    TimelineEvent has its coded evidence stripped before any signal
    extractor sees it. Leaves ``text_snippet`` intact, so only the
    text_channel can fire. This simulates running the detector BEFORE
    the coding pipeline has enriched the graph.
    """

    from services.analysis_worker.app.episode_detector_v2 import (
        runner as runner_module,
    )

    original = runner_module.load_timeline

    async def _text_only_load_timeline(patient_id: str, client: Any):
        events = await original(patient_id, client)
        stripped: list[Any] = []
        for ev in events:
            stripped.append(
                dataclasses.replace(
                    ev,
                    coded_entities=(),
                    observation_results=(),
                    referral_form=None,
                )
            )
        return stripped

    runner_module.load_timeline = _text_only_load_timeline


def _install_v1_bundle() -> list[str]:
    """Install the champion bundle with every v1 rulebook that ships
    on disk. Returns the list of sites that got a v1 upgrade (the
    others stay on v0). Prints a one-line banner so the dry-run
    caller can see which rulebook the detector is using.
    """

    from libs.episode_detector.loader import (
        DEFAULTS_DIR,
        load_default_bundle,
        load_rulebook,
        override_sites,
        set_current_bundle,
    )

    bundle = load_default_bundle()
    overrides = {}
    for path in sorted(Path(DEFAULTS_DIR).glob("*.v1.json")):
        rb = load_rulebook(path)
        overrides[rb.site_key] = rb
    if overrides:
        bundle = override_sites(bundle, overrides)
    set_current_bundle(bundle)
    return sorted(overrides.keys())


_WRITE_TOKENS = ("MERGE", "CREATE", "SET", "DELETE", "DETACH", "REMOVE")
# Match a write token as a standalone Cypher keyword (word-boundary on
# both sides) anywhere in the query. Covers " MERGE ", "\nMERGE ",
# "(MERGE ", and the bare clause at end-of-line.
_WRITE_RE = re.compile(
    r"\b(?:" + "|".join(_WRITE_TOKENS) + r")\b",
    re.IGNORECASE,
)


class _ReadOnlyClient:
    """Adapter that delegates reads, swallows writes."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.write_count = 0
        self.suppressed_writes: list[tuple[str, dict[str, Any]]] = []

    def _is_write(self, cypher: str) -> bool:
        return bool(_WRITE_RE.search(cypher))

    def run(self, cypher: str, **params: Any) -> Any:
        if self._is_write(cypher):
            self.write_count += 1
            self.suppressed_writes.append((cypher, params))
            preview = " ".join(cypher.split())[:80]
            logger.info("[dry-run] suppressed write Cypher: %s...", preview)
            return []
        return self._inner.run(cypher, **params)

    def session(self):
        return self._inner.session()

    def close(self) -> None:
        if hasattr(self._inner, "close"):
            self._inner.close()


def _summarise_proposed_episodes(
    suppressed_writes: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Pull the Episode rows out of the suppressed MERGE payload."""
    proposed: list[dict[str, Any]] = []
    for cypher, params in suppressed_writes:
        if "MERGE (e:Episode" not in cypher:
            continue
        for ep in params.get("episodes", []) or []:
            proposed.append(ep)
    return proposed


def _print_episode(idx: int, ep: dict[str, Any]) -> None:
    print(
        f"  [{idx}] site={ep.get('site_key'):<20} "
        f"tier={ep.get('confidence_tier'):<7} "
        f"status={ep.get('status'):<14} "
        f"start={ep.get('start_date')} end={ep.get('end_date')}"
    )
    print(f"       episode_id={ep.get('episode_id')}")
    print(f"       encounters={len(ep.get('encounter_ids') or [])}")
    if ep.get("review_reasons"):
        print(f"       review_reasons={ep.get('review_reasons')}")


async def dry_run(
    patient_id: str,
    *,
    rulebook_version: str = "v1",
    text_only: bool = False,
) -> int:
    from libs.keyvault.loader import load_keyvault_secrets

    load_keyvault_secrets()

    v1_sites: list[str] = []
    if rulebook_version == "v1":
        v1_sites = _install_v1_bundle()

    from libs.neo4j_client.client import PatientGraphClient
    from services.analysis_worker.app.episode_detector_v2.normaliser import (
        load_timeline,
    )
    from services.analysis_worker.app.episode_detector_v2.runner import (
        build_episodes,
    )

    if text_only:
        _install_text_only_timeline()

    if v1_sites:
        print(f"[dry-run] v1 rulebooks installed for: {', '.join(v1_sites)}")
    else:
        print("[dry-run] running against v0 (shipped) rulebook bundle")
    if text_only:
        print(
            "[dry-run] TEXT-ONLY mode: coded_entities / observation_results "
            "/ referral_form stripped -- only text_channel can fire."
        )

    inner = PatientGraphClient()
    client = _ReadOnlyClient(inner)
    try:
        timeline = await load_timeline(patient_id, client)
        result = await build_episodes(
            patient_id=patient_id,
            anchors=None,
            patient_client=client,
            domain_id="",
        )
    finally:
        client.close()

    print("=" * 78)
    print(f"Episode Detector v2 dry-run for patient {patient_id}")
    print("=" * 78)
    print(f"Timeline events loaded:          {len(timeline)}")
    print(f"Auto-published episodes:         {result.episodes_created}")
    print(f"Review-required candidates:      {result.review_count}")
    print(f"Encounters linked (auto):        {result.encounters_linked}")
    print(f"Suppressed write Cypher count:   {client.write_count}")
    if result.errors:
        print(f"Errors:                          {result.errors}")
    print()

    proposed = _summarise_proposed_episodes(client.suppressed_writes)
    if proposed:
        print("Proposed AUTO episodes (would persist):")
        for i, ep in enumerate(proposed, start=1):
            _print_episode(i, ep)
        print()

    # Also print the review / suggest tiers so a dry-run against a real
    # patient shows every resolved proposal, not just the auto ones that
    # would be written to Neo4j. Encounter IDs are included so the caller
    # can diff against a manual reviewer's membership.
    non_auto = [ep for ep in result.resolved_episodes if ep.confidence_tier != "auto"]
    if non_auto:
        print("Proposed REVIEW / SUGGEST episodes (would NOT persist):")
        for i, ep in enumerate(non_auto, start=1):
            print(
                f"  [{i}] site={ep.site_key:<20} "
                f"tier={ep.confidence_tier:<7} "
                f"status={ep.status:<14} intent={ep.intent:<10} "
                f"start={ep.start_date} end={ep.end_date}"
            )
            print(f"       episode_id={ep.episode_id}")
            print(f"       encounters={len(ep.encounter_ids)}")
            print(f"       review_reasons={ep.review_reasons}")
            print(f"       encounter_ids={list(ep.encounter_ids)}")
        print()

    # Include encounter IDs for auto-tier proposals too. The Neo4j write
    # payload already has them, but printing inline keeps the diff with
    # the manual reviewer in one place.
    if proposed:
        print("AUTO episode encounter IDs:")
        for ep in proposed:
            print(f"  {ep.get('episode_id')} -> {list(ep.get('encounter_ids') or [])}")
        print()

    if result.coverage_report is not None:
        cov = result.coverage_report
        n_total = len(cov.encounter_ids_total)
        n_in = len(cov.encounter_ids_in_episodes)
        n_adj = len(cov.encounter_ids_adjacent_to_active_episode)
        n_none = len(cov.encounter_ids_no_signal)
        n_un = len(cov.encounter_ids_unaccounted)
        print("Coverage report:")
        print(f"  total encounters:               {n_total}")
        print(f"  in_episodes:                    {n_in}")
        print(f"  adjacent_to_active_episode:     {n_adj}")
        print(f"  no_signal:                      {n_none}")
        print(f"  unaccounted (review needed):    {n_un}")
        if cov.encounter_ids_unaccounted:
            print("  unaccounted ids (first 10):")
            for enc in list(cov.encounter_ids_unaccounted)[:10]:
                print(f"    - {enc}")
        if cov.encounter_ids_adjacent_to_active_episode:
            print("  adjacent ids (first 10):")
            for enc in list(cov.encounter_ids_adjacent_to_active_episode)[:10]:
                print(f"    - {enc}")
    return 0


def _cli_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient-id", required=True)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--rulebook-version",
        choices=["v0", "v1"],
        default="v1",
        help="Which bundle to install before running (default: v1).",
    )
    parser.add_argument(
        "--text-only",
        action="store_true",
        help=(
            "Strip coded SNOMEDs / observations / referral forms from the "
            "timeline before the detector sees it. Only the text_channel "
            "regex catalogue can fire. Use this to measure what the "
            "detector could propose BEFORE coding runs, so coding effort "
            "can be restricted to the encounters that land in a candidate "
            "episode."
        ),
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    return asyncio.run(
        dry_run(
            args.patient_id,
            rulebook_version=args.rulebook_version,
            text_only=args.text_only,
        )
    )


if __name__ == "__main__":
    raise SystemExit(_cli_main())
