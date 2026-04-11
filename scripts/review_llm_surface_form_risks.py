#!/usr/bin/env python3
"""Flag potentially risky LLM-added surface forms for manual review."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "exports" / "ner" / "llm_surface_form_expand_report.json"
DEFAULT_OUTPUT = ROOT / "exports" / "ner" / "llm_surface_form_risky_review.json"

AMBIGUOUS_TOKENS = {
    "ca",
    "nss",
    "fta",
    "2ww",
    "gi",
    "lgi",
    "ugi",
    "cns",
    "ent",
    "opd",
    "cae",
}
CLINICAL_CONTEXT_TOKENS = {
    "cancer",
    "skin",
    "breast",
    "lung",
    "bowel",
    "cervical",
    "gynae",
    "urology",
    "haematology",
    "head",
    "neck",
    "brain",
    "colorectal",
    "referral",
    "screening",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--min-risk-score", type=int, default=2)
    p.add_argument("--top", type=int, default=200)
    return p.parse_args()


def _tokenize(term: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+", term.lower())


def _risk_signals(term: str, decision: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    tokens = _tokenize(term)
    low = term.lower().strip()

    # 1) Very short terms are often ambiguous.
    if len(tokens) == 1 and len(tokens[0]) <= 4:
        reasons.append("short_single_token")

    # 2) Acronym-heavy text (e.g., mostly uppercase shorthand).
    letters = [c for c in term if c.isalpha()]
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio >= 0.7 and len(term) <= 14:
            reasons.append("acronym_heavy")

    # 3) Ambiguous shorthand token present.
    if any(tok in AMBIGUOUS_TOKENS for tok in tokens):
        reasons.append("contains_ambiguous_token")

    # 4) Generic referral phrasing without strong site/context anchor.
    if ("referral" in tokens or "urgent" in tokens) and not any(
        t in CLINICAL_CONTEXT_TOKENS for t in tokens
    ):
        reasons.append("generic_referral_phrase")

    # 5) Weak support in report metadata.
    evidence = int(decision.get("evidence_count", 0))
    if evidence <= 2:
        reasons.append("low_evidence_count")
    if len(decision.get("models", [])) <= 1:
        reasons.append("single_model_support")

    # 6) Suspiciously terse phrases.
    if len(low) <= 8 and " " not in low:
        reasons.append("very_short_phrase")

    return reasons


def main() -> None:
    args = parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    concept_reports = payload.get("concept_reports", [])

    flagged: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()

    for cr in concept_reports:
        concept_id = str(cr.get("concept_id", ""))
        preferred = str(cr.get("preferred_term", ""))
        accepted = set(cr.get("accepted", []) or [])
        decisions = cr.get("decisions", []) or []
        for d in decisions:
            term = str(d.get("term", "")).strip()
            if term not in accepted:
                continue
            signals = _risk_signals(term, d)
            risk_score = len(signals)
            if risk_score < args.min_risk_score:
                continue
            for s in signals:
                reason_counts[s] += 1
            flagged.append(
                {
                    "concept_id": concept_id,
                    "preferred_term": preferred,
                    "term": term,
                    "risk_score": risk_score,
                    "risk_signals": signals,
                    "models": d.get("models", []),
                    "max_confidence": d.get("max_confidence"),
                    "evidence_count": d.get("evidence_count"),
                }
            )

    flagged.sort(key=lambda x: (-x["risk_score"], x["term"].lower()))
    top = flagged[: args.top]
    out = {
        "source_report": str(args.input),
        "total_accepted_terms": int(payload.get("accepted_terms_total", 0)),
        "flagged_terms_total": len(flagged),
        "returned_top_n": len(top),
        "min_risk_score": args.min_risk_score,
        "risk_signal_counts": dict(reason_counts),
        "items": top,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "flagged_terms_total": len(flagged),
                "returned_top_n": len(top),
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
