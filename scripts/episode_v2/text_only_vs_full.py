"""Text-only vs full-coding comparison for the episode detector.

Atlas trace:
  DI: DI-8A5FCF4F (detector)
  DI: DI-FA3CE229 (RulebookBundle runtime)
  Target DI (to be created): detector-first coding triage

For each patient in ``GOLD_PATIENTS`` we run the v2 detector twice:

1. **Full**: coded_entities, observations, and referral_form all
   visible. This is the production path. The set of encounters that
   land in a resolved auto/suggest/review episode is the
   "full_in_episode" ground truth.

2. **Text-only**: coded evidence stripped from every TimelineEvent so
   only the text_channel can fire. Encounters whose text matches a
   site regex land as text_signal; we then take the text-only
   resolved episodes' membership plus every encounter that emitted
   a text_signal (because those are the encounters we would code).

We report:

* **recall**  = |text_signal ∩ full_in_episode| / |full_in_episode|
  (what fraction of the full-coding episode membership would we
  still code if we pre-filtered using only text signals?)
* **coding_saved** = 1 - |text_signal| / total_encounters
  (what fraction of encounters can skip the NER pipeline?)

This is a rough accuracy view, not a replacement for a labelled VT.
It lets us decide whether building a dedicated "coding triage"
pathway is worth the Atlas artefact chain.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

GOLD_PATIENTS: tuple[str, ...] = ("4246897485", "4920262426", "6282779235")


def _install_v1_bundle() -> None:
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
    set_current_bundle(override_sites(bundle, overrides))


async def _run_once(patient_id: str, *, text_only: bool) -> dict[str, Any]:
    from libs.neo4j_client.client import PatientGraphClient
    from scripts.episode_v2.dry_run_patient import _ReadOnlyClient
    from services.analysis_worker.app.episode_detector_v2 import (
        runner as runner_module,
    )
    from services.analysis_worker.app.episode_detector_v2.normaliser import (
        load_timeline,
    )
    from services.analysis_worker.app.episode_detector_v2.signals import (
        extract_code_signals,
        extract_pathway_signals,
        extract_result_signals,
        extract_text_signals,
        extract_treatment_signals,
    )

    original_loader = runner_module.load_timeline
    if text_only:

        async def _text_only_loader(pid: str, client: Any):
            raw_events = await load_timeline(pid, client)
            return [
                dataclasses.replace(
                    ev,
                    coded_entities=(),
                    observation_results=(),
                    referral_form=None,
                )
                for ev in raw_events
            ]

        runner_module.load_timeline = _text_only_loader

    inner = PatientGraphClient()
    client = _ReadOnlyClient(inner)
    try:
        timeline = await load_timeline(patient_id, inner)
        result = await runner_module.build_episodes(
            patient_id=patient_id,
            anchors=None,
            patient_client=client,
            domain_id="",
        )
    finally:
        client.close()
        if text_only:
            runner_module.load_timeline = original_loader

    effective_timeline = timeline
    if text_only:
        effective_timeline = [
            dataclasses.replace(
                ev,
                coded_entities=(),
                observation_results=(),
                referral_form=None,
            )
            for ev in timeline
        ]

    signals = (
        extract_code_signals(effective_timeline)
        + extract_text_signals(effective_timeline)
        + extract_pathway_signals(effective_timeline)
        + extract_result_signals(effective_timeline)
        + extract_treatment_signals(effective_timeline)
    )

    all_encounter_ids = [ev.encounter_id for ev in timeline]
    signal_encounter_ids = {s.encounter_id for s in signals}
    text_signal_encounter_ids = {s.encounter_id for s in signals if s.channel == "text"}

    in_episode_ids: set[str] = set()
    for ep in result.resolved_episodes:
        in_episode_ids.update(ep.encounter_ids)

    return {
        "patient_id": patient_id,
        "text_only": text_only,
        "total_encounters": len(all_encounter_ids),
        "signal_encounters": sorted(signal_encounter_ids),
        "text_signal_encounters": sorted(text_signal_encounter_ids),
        "in_episode_encounters": sorted(in_episode_ids),
        "resolved_episode_count": len(result.resolved_episodes),
        "auto_episode_count": result.episodes_created,
        "review_episode_count": result.review_count,
    }


def _compare(full: dict[str, Any], text_only: dict[str, Any]) -> dict[str, Any]:
    full_set = set(full["in_episode_encounters"])
    text_signal_set = set(text_only["text_signal_encounters"])
    text_in_ep_set = set(text_only["in_episode_encounters"])

    recall_signal = len(text_signal_set & full_set) / len(full_set) if full_set else 0.0
    recall_episode = len(text_in_ep_set & full_set) / len(full_set) if full_set else 0.0
    total = full["total_encounters"] or 1
    coding_saved = 1 - (len(text_signal_set) / total)

    return {
        "patient_id": full["patient_id"],
        "total_encounters": full["total_encounters"],
        "full_in_episode": len(full_set),
        "text_signal_count": len(text_signal_set),
        "text_in_episode": len(text_in_ep_set),
        "recall_signal": round(recall_signal, 3),
        "recall_episode": round(recall_episode, 3),
        "coding_saved": round(coding_saved, 3),
        "full_auto_episodes": full["auto_episode_count"],
        "full_review_episodes": full["review_episode_count"],
        "text_only_auto_episodes": text_only["auto_episode_count"],
        "text_only_review_episodes": text_only["review_episode_count"],
    }


async def main_async() -> int:
    from libs.keyvault.loader import load_keyvault_secrets

    load_keyvault_secrets()
    _install_v1_bundle()

    results: list[dict[str, Any]] = []
    for pid in GOLD_PATIENTS:
        full = await _run_once(pid, text_only=False)
        text_only = await _run_once(pid, text_only=True)
        row = _compare(full, text_only)
        results.append(row)

    print()
    print("=" * 96)
    print(
        f"{'patient':<12} {'encs':>5} {'full_ep':>7} "
        f"{'txt_sig':>7} {'txt_ep':>6} "
        f"{'rec_sig':>7} {'rec_ep':>6} "
        f"{'save':>5} {'full_auto/rev':>13} {'txt_auto/rev':>12}"
    )
    print("-" * 96)
    for r in results:
        print(
            f"{r['patient_id']:<12} {r['total_encounters']:>5} "
            f"{r['full_in_episode']:>7} "
            f"{r['text_signal_count']:>7} {r['text_in_episode']:>6} "
            f"{r['recall_signal']:>7.2f} {r['recall_episode']:>6.2f} "
            f"{r['coding_saved']:>5.2f} "
            f"{r['full_auto_episodes']}/{r['full_review_episodes']:<11} "
            f"{r['text_only_auto_episodes']}/{r['text_only_review_episodes']}"
        )
    print("=" * 96)
    print()
    print("rec_sig = recall of text_signal encounters vs full in-episode set")
    print(
        "rec_ep  = recall of text-only resolved episodes' encounters vs "
        "full in-episode set"
    )
    print("save    = fraction of encounters that would skip coding")
    print()
    print(json.dumps(results, indent=2))
    return 0


def _cli_main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(_cli_main())
