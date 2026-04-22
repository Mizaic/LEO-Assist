"""Release a retrained EpisodeScorer to the graph as a versioned node.

Atlas trace:
  DI: DI-8A5FCF4F (Defence-in-depth episode detector with coverage fail-safe)

Persists the output of `libs.episode_learning.scorer_retrain.retrain_site_scorer`
(plus the champion/challenger evaluation report) as an
``:EpisodeScorerVersion`` node so retrain history is queryable from
the graph and not buried in repo branches.

Schema (one node per release):

    (:EpisodeScorerVersion {
        version_id: str,                 -- 'breast-2026-04-22-001'
        site_key: str,
        weights_json: str,               -- json.dumps(weights dict)
        sample_count: int,
        learning_rate: float,
        iteration: int,
        evaluation_json: str,            -- serialised PromotionDecision
        promoted: bool,
        released_by: str,
        released_at: datetime,
        notes: str
    })

Entry point: ``release_scorer(...)`` is pure on its inputs and a thin
graph_client adapter; the CLI is intentionally lightweight.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from libs.episode_learning.champion_challenger import (
    PromotionDecision,
    serialise_decision,
)
from libs.episode_learning.scorer_retrain import ScorerWeights

logger = logging.getLogger(__name__)


class GraphRunner(Protocol):
    """Minimal protocol for a Neo4j-style runner used by release_scorer."""

    def run(self, cypher: str, **params: Any) -> Any: ...


@dataclass(frozen=True)
class ReleaseRecord:
    """Persisted release record for a single site scorer version."""

    version_id: str
    site_key: str
    promoted: bool
    sample_count: int
    iteration: int
    released_at: datetime


WRITE_SCORER_VERSION = """
MERGE (v:EpisodeScorerVersion {version_id: $version_id})
SET v.site_key       = $site_key,
    v.weights_json   = $weights_json,
    v.sample_count   = $sample_count,
    v.learning_rate  = $learning_rate,
    v.iteration      = $iteration,
    v.evaluation_json = $evaluation_json,
    v.promoted       = $promoted,
    v.released_by    = $released_by,
    v.released_at    = datetime($released_at),
    v.notes          = $notes
RETURN v.version_id AS version_id
"""


def _build_version_id(site_key: str, released_at: datetime) -> str:
    stamp = released_at.strftime("%Y-%m-%d")
    return f"{site_key}-{stamp}-{uuid.uuid4().hex[:8]}"


def release_scorer(
    runner: GraphRunner,
    *,
    weights: ScorerWeights,
    decision: PromotionDecision,
    released_by: str,
    notes: str = "",
    released_at: datetime | None = None,
) -> ReleaseRecord:
    """Persist a versioned scorer record to the graph.

    The function never raises on a missing audit field; it always
    returns a ReleaseRecord so the caller can write a follow-up
    audit entry. The actual rollout (flipping the live scorer)
    happens elsewhere -- this function just records evidence.
    """
    when = released_at or datetime.now(timezone.utc)
    version_id = _build_version_id(weights.site_key, when)
    params: Mapping[str, Any] = {
        "version_id": version_id,
        "site_key": weights.site_key,
        "weights_json": json.dumps(weights.weights, sort_keys=True),
        "sample_count": weights.sample_count,
        "learning_rate": weights.learning_rate,
        "iteration": weights.iteration,
        "evaluation_json": json.dumps(serialise_decision(decision)),
        "promoted": bool(decision.promote),
        "released_by": released_by,
        "released_at": when.isoformat(),
        "notes": notes,
    }
    runner.run(WRITE_SCORER_VERSION, **params)
    record = ReleaseRecord(
        version_id=version_id,
        site_key=weights.site_key,
        promoted=bool(decision.promote),
        sample_count=weights.sample_count,
        iteration=weights.iteration,
        released_at=when,
    )
    logger.info(
        "Released scorer version=%s site=%s promoted=%s samples=%d",
        record.version_id,
        record.site_key,
        record.promoted,
        record.sample_count,
    )
    return record


def _cli_main(argv: list[str] | None = None) -> int:
    """Lightweight CLI for ad-hoc releases.

    Reads a JSON payload of {weights: ScorerWeights-like, decision: PromotionDecision-like}
    from stdin and prints the resulting version_id. The graph runner
    is constructed lazily so the CLI is import-safe in tests.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--released-by", required=True)
    parser.add_argument("--notes", default="")
    args = parser.parse_args(argv)
    payload = json.load(sys.stdin)
    weights_payload = payload["weights"]
    decision_payload = payload["decision"]

    weights = ScorerWeights(
        site_key=weights_payload["site_key"],
        weights=dict(weights_payload["weights"]),
        sample_count=int(weights_payload.get("sample_count", 0)),
        learning_rate=float(weights_payload.get("learning_rate", 0.0)),
        iteration=int(weights_payload.get("iteration", 1)),
        notes=str(weights_payload.get("notes", "")),
    )

    from libs.episode_learning.champion_challenger import EvaluationResult

    def _eval(node: Mapping[str, Any]) -> EvaluationResult:
        return EvaluationResult(
            label=str(node.get("label", "")),
            site_key=str(node["site_key"]),
            precision=float(node["precision"]),
            recall=float(node["recall"]),
            f1=float(node["f1"]),
            cases_evaluated=int(node["cases_evaluated"]),
        )

    decision = PromotionDecision(
        promote=bool(decision_payload["promote"]),
        rationale=str(decision_payload.get("rationale", "")),
        champion=_eval(decision_payload["champion"]),
        challenger=_eval(decision_payload["challenger"]),
    )

    from libs.graph_client import patient_graph_client

    runner = patient_graph_client.PatientGraphClient()
    try:
        record = release_scorer(
            runner,
            weights=weights,
            decision=decision,
            released_by=args.released_by,
            notes=args.notes,
        )
    finally:
        if hasattr(runner, "close"):
            runner.close()

    json.dump(
        {
            "version_id": record.version_id,
            "site_key": record.site_key,
            "promoted": record.promoted,
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
