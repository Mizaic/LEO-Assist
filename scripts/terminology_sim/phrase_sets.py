"""Build the simulation phrase sets as JSON case lists.

Sets:
  labelled  -- VAL-41005BA4 facts (the lookup term the pipeline sent).
  human_sf  -- surface forms people made (reviewers, curators). Read-only
               knowledge graph query. Scored in "hidden" mode so the
               phrase cannot simply match itself.
  hard      -- named hard cases, tests/fixtures/terminology_sim/.

Each set also gets <set>.strip.json: the same phrases without onset or
duration wording, for the "strip" strategies.

Usage:
    python -m scripts.terminology_sim.phrase_sets OUT_DIR
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from libs.neo4j_client.client import KnowledgeGraphClient
from libs.terminology.surface_normalize import normalize_surface
from scripts.terminology_sim.env import load_local_env
from scripts.terminology_sim.features import strip_qualifiers
from scripts.terminology_sim.pool import Case

_ROOT = Path(__file__).resolve().parents[2]
LABELLED_REPORT = (
    _ROOT
    / "tests/fixtures/clinical_extraction_scenarios/reports"
    / "val_41005ba4_terminology_resolve.json"
)
HARD_CASES = _ROOT / "tests/fixtures/terminology_sim/hard_cases.json"

HUMAN_SOURCES = (
    "gold_label_editor",
    "manual",
    "manual_pin",
    "manual_curation",
    "coding_review",
    "batch_coding_review",
    "manual_mapping",
)

_HUMAN_SF = """
MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept)
WHERE c.active = true
  AND sf.source IN $sources
  AND coalesce(sf.status, 'approved') IN ['approved', 'active']
  AND coalesce(c.is_local, false) = false
RETURN sf.form AS form, sf.normalized AS norm,
       collect(DISTINCT c.id) AS ids,
       collect(c.semantic_tag) AS tags
"""


def _labelled_case(case_id: str, fact: dict[str, Any]) -> Case | None:
    phrase = str(fact.get("lookup_term") or fact.get("surface_form") or "")
    expected = str(fact.get("expected_concept_id") or "").strip()
    no_code = bool(fact.get("expected_no_code") or fact.get("expected_withhold"))
    if not phrase or not (expected or no_code):
        return None
    return Case(
        case_id=case_id,
        phrase=phrase,
        tag=str(fact.get("expected_semantic_tag") or ""),
        expected=[expected] if expected else [],
        expect_no_code=no_code and not expected,
        source="labelled",
    )


def labelled_cases(report: Path = LABELLED_REPORT) -> list[Case]:
    data = json.loads(report.read_text(encoding="utf-8"))
    seen: dict[tuple[str, str], Case] = {}
    for scenario in data["cases"]:
        for i, fact in enumerate(scenario.get("facts") or []):
            case = _labelled_case(f"{scenario['case_id']}#{i}", fact)
            if case is None:
                continue
            seen.setdefault((normalize_surface(case.phrase), case.tag), case)
    return list(seen.values())


def human_sf_cases(session) -> list[Case]:
    cases = []
    for rec in session.run(_HUMAN_SF, sources=list(HUMAN_SOURCES)):
        tag = Counter(t for t in rec["tags"] if t).most_common(1)
        cases.append(
            Case(
                case_id=f"sf:{rec['norm']}",
                phrase=str(rec["form"]),
                tag=tag[0][0] if tag else "",
                expected=sorted(str(i) for i in rec["ids"]),
                source="human_sf",
            )
        )
    return cases


def hard_cases(path: Path = HARD_CASES) -> list[Case]:
    return [Case(**row) for row in json.loads(path.read_text(encoding="utf-8"))]


def stripped_cases(cases: list[Case]) -> list[Case]:
    """One extra case per phrase whose onset/duration wording can be dropped."""
    out = []
    for case in cases:
        bare = strip_qualifiers(case.phrase)
        if not bare or normalize_surface(bare) == normalize_surface(case.phrase):
            continue
        out.append(replace(case, case_id=case.case_id + "|strip", phrase=bare))
    return out


def _write(path: Path, cases: list[Case]) -> None:
    path.write_text(json.dumps([asdict(c) for c in cases], indent=1), "utf-8")
    print(f"{path.name}: {len(cases)} cases")
    if not path.stem.endswith(".strip"):
        _write(path.with_suffix(".strip.json"), stripped_cases(cases))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    _write(args.out_dir / "labelled.json", labelled_cases())
    _write(args.out_dir / "hard.json", hard_cases())
    load_local_env()
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            _write(args.out_dir / "human_sf.json", human_sf_cases(session))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
