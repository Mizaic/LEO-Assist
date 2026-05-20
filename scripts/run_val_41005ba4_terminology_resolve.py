#!/usr/bin/env python3
"""Run VAL-41005BA4 step 1 against live terminology API.

Loads clinical facts (expected_strings) from extraction scenario fixtures,
resolves them through the terminology API, applies the production safe-attach
gate (_merge_resolution at 0.55), and writes a clinician-review report.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from libs.pipeline_graph.subgraphs.terminology import (  # noqa: E402
    _DEFAULT_MIN_SCORE,
    _merge_resolution,
)
from libs.terminology.client import ResolvedTerm, TerminologyClient  # noqa: E402
from tests.helpers.clinical_extraction_scenario_loader import iter_cases  # noqa: E402

REPORT_DIR = _REPO_ROOT / "tests/fixtures/clinical_extraction_scenarios/reports"
REPORT_JSON = REPORT_DIR / "val_41005ba4_terminology_resolve.json"
REPORT_CSV = REPORT_DIR / "val_41005ba4_terminology_resolve.csv"
VAL_ID = "VAL-41005BA4"
RESOLVE_BATCH = 30
# Withhold is the clinically correct outcome; safe attach would be a VAL failure.
_EXPECTED_WITHHOLD_SURFACES = frozenset({"aneurysm clip"})


def _candidate_dict(term: ResolvedTerm) -> dict[str, Any]:
    return {
        "concept_id": term.concept_id,
        "term": term.term,
        "semantic_tag": term.semantic_tag,
        "score": round(float(term.score or 0), 4),
        "read_code": term.read_code,
        "had_exact_match": term.had_exact_match,
        "lexical_raw": round(float(term.lexical_raw or 0), 4),
        "vector_raw": round(float(term.vector_raw or 0), 4),
    }


def _unresolved_reason(
    surface_form: str,
    candidates: list[ResolvedTerm],
    merged: dict[str, Any],
) -> str | None:
    if not merged.get("terminology_unresolved"):
        return None
    if not candidates:
        return "no_candidates"
    best = candidates[0]
    from libs.pipeline_graph.subgraphs import terminology as terminology_mod

    if terminology_mod._is_blocked_mapping(surface_form, best.concept_id):
        return "blocklisted"
    if float(best.score or 0) < _DEFAULT_MIN_SCORE:
        return "below_threshold"
    return "unresolved"


def _resolve_all_terms(
    client: TerminologyClient, terms: list[str]
) -> dict[str, list[ResolvedTerm]]:
    results: dict[str, list[ResolvedTerm]] = {}
    for i in range(0, len(terms), RESOLVE_BATCH):
        chunk = terms[i : i + RESOLVE_BATCH]
        results.update(client.resolve(chunk))
    return results


def _normalise_surface(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _val_result(fact: dict[str, Any]) -> str:
    surface = _normalise_surface(str(fact.get("surface_form") or ""))
    safe_attached = bool(fact.get("safe_attached"))
    if surface in _EXPECTED_WITHHOLD_SURFACES:
        return "pass" if not safe_attached and not fact.get("concept_id") else "fail"
    return "pass" if safe_attached else "fail"


def _build_fact_row(
    surface_form: str,
    candidates: list[ResolvedTerm],
) -> dict[str, Any]:
    entity = {"text": surface_form}
    merged = _merge_resolution(entity, candidates, _DEFAULT_MIN_SCORE)
    top_candidates = [_candidate_dict(c) for c in candidates[:3]]
    fact = {
        "surface_form": surface_form,
        "lookup_term": surface_form,
        "expected_withhold": _normalise_surface(surface_form)
        in _EXPECTED_WITHHOLD_SURFACES,
        "safe_attached": not bool(merged.get("terminology_unresolved")),
        "concept_id": merged.get("concept_id"),
        "preferred_term": merged.get("term"),
        "semantic_tag": merged.get("semantic_tag"),
        "read_code": merged.get("read_code"),
        "score": merged.get("score"),
        "terminology_unresolved": bool(merged.get("terminology_unresolved")),
        "unresolved_reason": _unresolved_reason(surface_form, candidates, merged),
        "top_candidates": top_candidates,
    }
    fact["val_result"] = _val_result(fact)
    return fact


def _write_csv(rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "case_id",
        "site",
        "format",
        "surface_form",
        "safe_attached",
        "concept_id",
        "preferred_term",
        "semantic_tag",
        "score",
        "terminology_unresolved",
        "unresolved_reason",
        "expected_withhold",
        "val_result",
        "top_candidate_concept_id",
        "top_candidate_term",
        "top_candidate_score",
    ]
    with REPORT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            top = (row.get("top_candidates") or [{}])[0]
            writer.writerow(
                {
                    "case_id": row["case_id"],
                    "site": row["site"],
                    "format": row["format"],
                    "surface_form": row["surface_form"],
                    "safe_attached": row["safe_attached"],
                    "concept_id": row.get("concept_id") or "",
                    "preferred_term": row.get("preferred_term") or "",
                    "semantic_tag": row.get("semantic_tag") or "",
                    "score": row.get("score") if row.get("score") is not None else "",
                    "terminology_unresolved": row["terminology_unresolved"],
                    "unresolved_reason": row.get("unresolved_reason") or "",
                    "expected_withhold": row.get("expected_withhold", False),
                    "val_result": row.get("val_result") or "",
                    "top_candidate_concept_id": top.get("concept_id") or "",
                    "top_candidate_term": top.get("term") or "",
                    "top_candidate_score": top.get("score") if top.get("score") else "",
                }
            )


def main() -> int:
    api_url = os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001").strip()
    cases = iter_cases()
    unique_terms = sorted(
        {
            str(value).strip()
            for case in cases
            for value in case.get("expected_strings") or []
            if str(value).strip()
        },
        key=str.lower,
    )
    if not unique_terms:
        print("No expected_strings found in extraction scenarios.", file=sys.stderr)
        return 1

    client = TerminologyClient(base_url=api_url, timeout=60.0, max_retries=2)
    print(f"Resolving {len(unique_terms)} unique terms via {api_url} ...")
    resolved_by_term = _resolve_all_terms(client, unique_terms)
    fact_by_term = {
        term: _build_fact_row(term, resolved_by_term.get(term, []))
        for term in unique_terms
    }

    case_reports: list[dict[str, Any]] = []
    csv_rows: list[dict[str, Any]] = []
    safe_count = 0
    unresolved_count = 0
    val_pass_count = 0
    val_fail_count = 0
    val_failures: list[dict[str, str]] = []
    total_facts = 0

    for case in cases:
        case_id = str(case.get("case_id") or "")
        facts: list[dict[str, Any]] = []
        for surface in case.get("expected_strings") or []:
            surface_form = str(surface).strip()
            if not surface_form:
                continue
            fact = dict(fact_by_term[surface_form])
            facts.append(fact)
            total_facts += 1
            if fact["safe_attached"]:
                safe_count += 1
            else:
                unresolved_count += 1
            if fact["val_result"] == "pass":
                val_pass_count += 1
            else:
                val_fail_count += 1
                val_failures.append(
                    {
                        "case_id": case_id,
                        "surface_form": surface_form,
                        "safe_attached": str(fact["safe_attached"]),
                        "concept_id": str(fact.get("concept_id") or ""),
                    }
                )
            csv_rows.append(
                {
                    "case_id": case_id,
                    "site": case.get("site") or "",
                    "format": case.get("format") or "",
                    **fact,
                }
            )
        case_reports.append(
            {
                "case_id": case_id,
                "site": case.get("site"),
                "format": case.get("format"),
                "source_markdown": case.get("source_markdown"),
                "phrase_classes": case.get("phrase_classes") or [],
                "facts": facts,
            }
        )

    by_reason: dict[str, int] = {}
    for term, fact in fact_by_term.items():
        if fact["safe_attached"]:
            continue
        reason = str(fact.get("unresolved_reason") or "unresolved")
        by_reason[reason] = by_reason.get(reason, 0) + 1

    report = {
        "schema_version": 1,
        "val_id": VAL_ID,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "terminology_api_url": api_url,
        "confidence_threshold": _DEFAULT_MIN_SCORE,
        "fixture_source": "tests/fixtures/clinical_extraction_scenarios/expected_strings.json",
        "summary": {
            "case_count": len(cases),
            "fact_occurrence_count": total_facts,
            "unique_surface_form_count": len(unique_terms),
            "safe_attached_count": safe_count,
            "unresolved_count": unresolved_count,
            "safe_attach_rate": round(safe_count / total_facts, 4) if total_facts else 0.0,
            "unique_unresolved_by_reason": by_reason,
            "val_pass_count": val_pass_count,
            "val_fail_count": val_fail_count,
            "val_pass_rate": round(val_pass_count / total_facts, 4) if total_facts else 0.0,
            "expected_withhold_surfaces": sorted(_EXPECTED_WITHHOLD_SURFACES),
            "val_failures": val_failures,
        },
        "cases": case_reports,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_csv(csv_rows)

    print(f"Wrote {REPORT_JSON}")
    print(f"Wrote {REPORT_CSV}")
    print(
        "Summary: "
        f"{len(cases)} cases, {total_facts} facts, "
        f"{safe_count} safe attached, {unresolved_count} unresolved "
        f"({report['summary']['safe_attach_rate']:.1%} attach rate)"
    )
    if by_reason:
        print(f"Unique unresolved reasons: {by_reason}")
    print(
        f"VAL check: {val_pass_count} pass, {val_fail_count} fail "
        f"({report['summary']['val_pass_rate']:.1%} pass rate)"
    )
    if val_failures:
        print("VAL failures:")
        for row in val_failures:
            print(
                f"  - {row['case_id']}: {row['surface_form']} "
                f"(safe_attached={row['safe_attached']}, concept_id={row['concept_id']})"
            )
    return 1 if val_fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
