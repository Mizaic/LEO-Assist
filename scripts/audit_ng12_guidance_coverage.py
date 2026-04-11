"""Run a deep NG12 guidance extraction coverage audit.

This script:
1) loads recommendations from /nice/{code}/subgraph
2) runs /guidance/rules/test/{rec_id} for each normative recommendation
3) classifies outcomes (success, partial, failed, http_error)
4) writes JSON + Markdown reports with actionable error buckets
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VAGUE_RE = re.compile(
    r"\b(associated symptoms|symptoms of|additional symptoms|additional signs|additional findings|take into account)\b",
    re.IGNORECASE,
)
INVESTIGATION_RE = re.compile(
    r"\b(x-?ray|ultrasound|ct|mri|endoscopy|blood test|full blood count|fit|ca125|measure)\b",
    re.IGNORECASE,
)
REFERRAL_RE = re.compile(
    r"\b(referral|suspected cancer pathway|2ww|2 week wait|fast track)\b",
    re.IGNORECASE,
)
THRESHOLD_RE = re.compile(
    r"(>=|<=|>|<|\bthreshold\b|\bper month\b|\bmicrograms?\b|\biu/ml\b|\bfirst presentation\b|\bpersistent\b|\bprogressive\b|\bsub-acute\b)",
    re.IGNORECASE,
)
SITE_SPECIFIC_RE = re.compile(
    r"\b(oesophageal|pancreatic|anal|oral|thyroid|myeloma|lymphoma|retinoblastoma|sarcoma|vulval|cervical|ovarian|testicular|urological|upper gastrointestinal|lower gastrointestinal)\b",
    re.IGNORECASE,
)


@dataclass
class RecommendationCase:
    rec_id: str
    guideline_id: str
    chapter_title: str
    section_title: str
    rec_title: str
    verbatim: str
    is_normative: bool


def _json_request(
    method: str,
    url: str,
    *,
    timeout: float = 300.0,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | None]:
    data = None
    headers = {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        url=url, method=method.upper(), data=data, headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            body = {"detail": raw or str(exc)}
        return int(exc.code), body if isinstance(body, dict) else {"detail": body}


_FETCH_GUIDELINE_RECS = """
MATCH (g:Guideline {id: $code})-[:HAS_CHAPTER]->(ch:Chapter)
OPTIONAL MATCH (ch)-[:HAS_RECOMMENDATION]->(r:Recommendation)
RETURN g.id AS guideline_id,
       ch.title AS chapter_title,
       ch.order AS chapter_order,
       r.id AS rec_id,
       r.sectionTitle AS section_title,
       r.title AS rec_title,
       r.verbatim AS verbatim,
       coalesce(r.isNormative, false) AS is_normative
ORDER BY chapter_order, rec_id
"""


def _prepare_runtime_env() -> None:
    root = Path(__file__).resolve().parents[1]
    try:
        from dotenv import load_dotenv

        load_dotenv(root / "secrets" / ".env.config", override=False)
        load_dotenv(root / "secrets" / ".env.secrets", override=False)
        load_dotenv(root / "secrets" / ".env", override=False)
    except Exception:
        pass

    # Best effort: if Key Vault URL is configured, pull latest secrets.
    try:
        from libs.keyvault.loader import load_keyvault_secrets

        load_keyvault_secrets()
    except Exception:
        pass


def _logic_leaf_count(node: dict[str, Any] | None) -> int:
    if not isinstance(node, dict):
        return 0
    kind = str(node.get("kind") or "").upper()
    if kind == "CONCEPT":
        return 1
    return sum(
        _logic_leaf_count(ch)
        for ch in (node.get("children") or [])
        if isinstance(ch, dict)
    )


def _collect_search_term_lengths(node: dict[str, Any] | None, out: list[int]) -> None:
    if not isinstance(node, dict):
        return
    kind = str(node.get("kind") or "").lower()
    if kind == "concept":
        term = node.get("term") or {}
        search_terms = term.get("search_terms") if isinstance(term, dict) else None
        if isinstance(search_terms, list):
            out.append(len([s for s in search_terms if str(s).strip()]))
        else:
            out.append(0)
        return
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _collect_search_term_lengths(child, out)


def _extract_error_prefixes(errors: list[str]) -> list[str]:
    prefixes = []
    for err in errors:
        if ":" in err:
            prefixes.append(err.split(":", 1)[0])
        else:
            prefixes.append(err)
    return prefixes


def _derive_failure_categories(
    *,
    recommendation_text: str,
    section_title: str,
    chapter_title: str,
    errors: list[str],
    error_prefixes: list[str],
) -> list[str]:
    """Bucket non-success cases into clinical outcome categories."""
    text = " ".join(
        [
            recommendation_text or "",
            section_title or "",
            chapter_title or "",
            " ".join(errors or []),
        ]
    ).lower()
    categories: list[str] = []
    if VAGUE_RE.search(text) or any(
        tok in text for tok in ("suggestive of", "compatible with", "consistent with")
    ):
        categories.append("vague_composite_findings")
    if INVESTIGATION_RE.search(text):
        categories.append("investigation_mapping")
    if REFERRAL_RE.search(text):
        categories.append("referral_mapping")
    if SITE_SPECIFIC_RE.search(text) and REFERRAL_RE.search(text):
        categories.append("site_specific_referral")
    if THRESHOLD_RE.search(text):
        categories.append("threshold_or_qualifier")
    if "verifier_unresolved" in error_prefixes:
        categories.append("verifier_unresolved")
    if "verifier_empty" in error_prefixes or "extraction_empty" in error_prefixes:
        categories.append("empty_or_operational")
    if not categories:
        categories.append("other")
    return sorted(set(categories))


def _run_case(
    base_url: str, case: RecommendationCase, timeout: float
) -> dict[str, Any]:
    encoded = urllib.parse.quote(case.rec_id, safe="")
    url = f"{base_url.rstrip('/')}/guidance/rules/test/{encoded}"
    started = time.perf_counter()
    status, body = _json_request("POST", url, timeout=timeout)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if not isinstance(body, dict):
        body = {"detail": "No JSON body returned."}

    errors = body.get("errors") if isinstance(body.get("errors"), list) else []
    error_prefixes = _extract_error_prefixes([str(e) for e in errors])
    coded = body.get("coded_criteria")
    raw = (
        body.get("raw_criteria") if isinstance(body.get("raw_criteria"), dict) else None
    )
    would_write = bool(body.get("would_write", False))
    logic_tree = (
        coded.get("logic_tree")
        if isinstance(coded, dict) and isinstance(coded.get("logic_tree"), dict)
        else None
    )
    leaf_count = _logic_leaf_count(logic_tree)

    search_term_lengths: list[int] = []
    if raw:
        _collect_search_term_lengths(
            raw.get("logic_tree") if isinstance(raw.get("logic_tree"), dict) else None,
            search_term_lengths,
        )

    if status >= 500:
        outcome = "http_error"
    elif status >= 400 and status != 422:
        outcome = "failed"
    elif coded is None:
        outcome = "failed"
    elif errors or not would_write:
        outcome = "partial"
    else:
        outcome = "success"
    failure_categories = (
        _derive_failure_categories(
            recommendation_text=case.verbatim,
            section_title=case.section_title,
            chapter_title=case.chapter_title,
            errors=[str(e) for e in errors],
            error_prefixes=error_prefixes,
        )
        if outcome != "success"
        else []
    )

    return {
        "rec_id": case.rec_id,
        "chapter_title": case.chapter_title,
        "section_title": case.section_title,
        "rec_title": case.rec_title,
        "is_normative": case.is_normative,
        "is_vague_clause": bool(VAGUE_RE.search(case.verbatim or "")),
        "status_code": status,
        "elapsed_ms": elapsed_ms,
        "outcome": outcome,
        "would_write": would_write,
        "leaf_count": leaf_count,
        "error_prefixes": error_prefixes,
        "errors": errors,
        "detail": body.get("detail"),
        "raw_search_term_lengths": search_term_lengths,
        "failure_categories": failure_categories,
    }


def _run_case_direct(case: RecommendationCase, subgraph: Any) -> dict[str, Any]:
    started = time.perf_counter()
    if not case.verbatim.strip():
        status = 422
        body: dict[str, Any] = {
            "detail": "Recommendation has no verbatim text stored.",
            "coded_criteria": None,
            "errors": [],
        }
    elif not case.is_normative:
        status = 422
        body = {
            "detail": "Recommendation is non-normative cross-reference.",
            "coded_criteria": None,
            "errors": [],
        }
    else:
        try:
            result = subgraph.invoke(
                {
                    "recommendation": {
                        "id": case.rec_id,
                        "verbatim": case.verbatim,
                        "title": case.rec_title,
                        "urgency": "",
                        "strength": "",
                        "section_title": case.section_title,
                        "chapter_title": case.chapter_title,
                    },
                    "guideline_id": case.guideline_id,
                }
            )
            body = {
                "coded_criteria": result.get("coded_criteria"),
                "raw_criteria": result.get("raw_criteria"),
                "errors": result.get("errors") or [],
                "would_write": result.get("coded_criteria") is not None
                and not any(
                    "terminology_api_unavailable" in str(e)
                    for e in (result.get("errors") or [])
                ),
            }
            status = 200 if body["coded_criteria"] is not None else 422
        except Exception as exc:
            status = 500
            body = {
                "detail": f"Extraction pipeline error: {exc}",
                "coded_criteria": None,
                "errors": [str(exc)],
            }
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if not isinstance(body, dict):
        body = {"detail": "No JSON body returned."}

    errors = body.get("errors") if isinstance(body.get("errors"), list) else []
    error_prefixes = _extract_error_prefixes([str(e) for e in errors])
    coded = body.get("coded_criteria")
    raw = (
        body.get("raw_criteria") if isinstance(body.get("raw_criteria"), dict) else None
    )
    would_write = bool(body.get("would_write", False))
    logic_tree = (
        coded.get("logic_tree")
        if isinstance(coded, dict) and isinstance(coded.get("logic_tree"), dict)
        else None
    )
    leaf_count = _logic_leaf_count(logic_tree)

    search_term_lengths: list[int] = []
    if raw:
        _collect_search_term_lengths(
            raw.get("logic_tree") if isinstance(raw.get("logic_tree"), dict) else None,
            search_term_lengths,
        )

    if status >= 500:
        outcome = "http_error"
    elif status >= 400 and status != 422:
        outcome = "failed"
    elif coded is None:
        outcome = "failed"
    elif errors or not would_write:
        outcome = "partial"
    else:
        outcome = "success"
    failure_categories = (
        _derive_failure_categories(
            recommendation_text=case.verbatim,
            section_title=case.section_title,
            chapter_title=case.chapter_title,
            errors=[str(e) for e in errors],
            error_prefixes=error_prefixes,
        )
        if outcome != "success"
        else []
    )

    return {
        "rec_id": case.rec_id,
        "chapter_title": case.chapter_title,
        "section_title": case.section_title,
        "rec_title": case.rec_title,
        "is_normative": case.is_normative,
        "is_vague_clause": bool(VAGUE_RE.search(case.verbatim or "")),
        "status_code": status,
        "elapsed_ms": elapsed_ms,
        "outcome": outcome,
        "would_write": would_write,
        "leaf_count": leaf_count,
        "error_prefixes": error_prefixes,
        "errors": errors,
        "detail": body.get("detail"),
        "raw_search_term_lengths": search_term_lengths,
        "failure_categories": failure_categories,
    }


def _load_recommendations(
    base_url: str, code: str, timeout: float
) -> list[RecommendationCase]:
    url = f"{base_url.rstrip('/')}/nice/{urllib.parse.quote(code)}/subgraph"
    status, body = _json_request("GET", url, timeout=timeout)
    if status >= 400 or not isinstance(body, dict):
        raise RuntimeError(f"Failed to load subgraph: HTTP {status} body={body}")
    chapters = body.get("chapters") if isinstance(body.get("chapters"), list) else []
    out: list[RecommendationCase] = []
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        chapter_title = str(ch.get("chapter_title") or "")
        for rec in ch.get("recommendations") or []:
            if not isinstance(rec, dict):
                continue
            out.append(
                RecommendationCase(
                    rec_id=str(rec.get("rec_id") or ""),
                    guideline_id=code,
                    chapter_title=chapter_title,
                    section_title=str(rec.get("section_title") or ""),
                    rec_title=str(rec.get("rec_title") or ""),
                    verbatim=str(rec.get("verbatim") or ""),
                    is_normative=bool(rec.get("is_normative")),
                )
            )
    return [r for r in out if r.rec_id]


def _load_recommendations_direct(code: str) -> list[RecommendationCase]:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    _prepare_runtime_env()
    from libs.neo4j_client.client import KnowledgeGraphClient

    client = KnowledgeGraphClient()
    try:
        rows = client.run(_FETCH_GUIDELINE_RECS, code=code)
    finally:
        client.close()
    if not rows:
        raise RuntimeError(f"Guideline {code} not found in knowledge graph.")

    out: list[RecommendationCase] = []
    for row in rows:
        rec_id = str(row.get("rec_id") or "")
        if not rec_id:
            continue
        out.append(
            RecommendationCase(
                rec_id=rec_id,
                guideline_id=str(row.get("guideline_id") or code),
                chapter_title=str(row.get("chapter_title") or ""),
                section_title=str(row.get("section_title") or ""),
                rec_title=str(row.get("rec_title") or ""),
                verbatim=str(row.get("verbatim") or ""),
                is_normative=bool(row.get("is_normative")),
            )
        )
    return [r for r in out if r.rec_id]


def _write_reports(
    code: str,
    results: list[dict[str, Any]],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"{code.lower()}-coverage-audit-{ts}.json"
    md_path = output_dir / f"{code.lower()}-coverage-audit-{ts}.md"

    outcome_counts = Counter(r["outcome"] for r in results)
    error_counts = Counter(err for r in results for err in r["error_prefixes"])
    category_counts = Counter(
        cat for r in results for cat in (r.get("failure_categories") or [])
    )
    vague = [r for r in results if r["is_vague_clause"]]
    vague_fail = [r for r in vague if r["outcome"] != "success"]
    slowest = sorted(results, key=lambda r: int(r["elapsed_ms"]), reverse=True)[:10]

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "code": code,
        "summary": {
            "total": len(results),
            "success": outcome_counts.get("success", 0),
            "partial": outcome_counts.get("partial", 0),
            "failed": outcome_counts.get("failed", 0),
            "http_error": outcome_counts.get("http_error", 0),
            "vague_total": len(vague),
            "vague_non_success": len(vague_fail),
        },
        "error_prefix_counts": dict(error_counts),
        "failure_category_counts": dict(category_counts),
        "results": results,
    }
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    lines = [
        f"# {code} guidance coverage audit",
        "",
        f"- Total audited: **{len(results)}**",
        f"- Success: **{outcome_counts.get('success', 0)}**",
        f"- Partial: **{outcome_counts.get('partial', 0)}**",
        f"- Failed: **{outcome_counts.get('failed', 0)}**",
        f"- HTTP errors: **{outcome_counts.get('http_error', 0)}**",
        f"- Vague-phrase recommendations: **{len(vague)}** (non-success: **{len(vague_fail)}**)",
        "",
        "## Top error buckets",
    ]
    if error_counts:
        for k, v in error_counts.most_common(12):
            lines.append(f"- `{k}`: {v}")
    else:
        lines.append("- None")
    lines += ["", "## Slowest recommendations", ""]
    for row in slowest:
        lines.append(
            f"- `{row['rec_id']}` — {row['elapsed_ms']} ms — {row['outcome']} "
            f"(status {row['status_code']})"
        )

    lines += ["", "## Non-success recommendations", ""]
    for row in [r for r in results if r["outcome"] != "success"]:
        errs = (
            ", ".join(row["error_prefixes"])
            if row["error_prefixes"]
            else (row.get("detail") or "")
        )
        lines.append(
            f"- `{row['rec_id']}` — {row['outcome']} (HTTP {row['status_code']})"
            + (f" — {errs}" if errs else "")
        )
    lines += ["", "## Outcome categories", ""]
    if category_counts:
        for k, v in category_counts.most_common():
            lines.append(f"- `{k}`: {v}")
    else:
        lines.append("- None")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit NG12 guidance extraction coverage."
    )
    parser.add_argument("--code", default="NG12", help="Guideline code (default: NG12)")
    parser.add_argument(
        "--api-base",
        default="http://localhost:3000/api",
        help="Base URL for proxied API (default: http://localhost:3000/api)",
    )
    parser.add_argument(
        "--mode",
        choices=["http", "direct"],
        default="direct",
        help="http: call API endpoints, direct: call router functions in-process (default: direct)",
    )
    parser.add_argument(
        "--timeout-seconds", type=float, default=300.0, help="Per-request timeout."
    )
    parser.add_argument(
        "--workers", type=int, default=3, help="Parallel workers for extraction tests."
    )
    parser.add_argument(
        "--output-dir",
        default="reports/guidance_coverage",
        help="Directory for JSON/Markdown report outputs.",
    )
    args = parser.parse_args()

    code = str(args.code or "NG12").strip().upper()
    if args.mode == "direct":
        recs = _load_recommendations_direct(code)
        root = Path(__file__).resolve().parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        _prepare_runtime_env()
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl import (
            build_guidance_rule_extraction_subgraph,
        )

        subgraph = build_guidance_rule_extraction_subgraph()
    else:
        recs = _load_recommendations(args.api_base, code, args.timeout_seconds)
        subgraph = None
    normative = [r for r in recs if r.is_normative and r.verbatim.strip()]
    if not normative:
        raise RuntimeError(
            f"No normative recommendations with verbatim text found for {code}."
        )

    print(
        f"Loaded {len(recs)} recommendations ({len(normative)} normative with text) for {code}."
    )
    started = time.perf_counter()

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, int(args.workers))
    ) as pool:
        if args.mode == "direct":
            futs = [pool.submit(_run_case_direct, rec, subgraph) for rec in normative]
        else:
            futs = [
                pool.submit(_run_case, args.api_base, rec, args.timeout_seconds)
                for rec in normative
            ]
        for idx, fut in enumerate(concurrent.futures.as_completed(futs), start=1):
            row = fut.result()
            results.append(row)
            if idx % 5 == 0 or idx == len(futs):
                print(
                    f"Progress {idx}/{len(futs)} "
                    f"(ok={sum(1 for r in results if r['outcome']=='success')}, "
                    f"partial={sum(1 for r in results if r['outcome']=='partial')}, "
                    f"failed={sum(1 for r in results if r['outcome'] in {'failed','http_error'})})"
                )

    elapsed = int((time.perf_counter() - started) * 1000)
    output_dir = Path(args.output_dir)
    json_path, md_path = _write_reports(
        code, sorted(results, key=lambda r: r["rec_id"]), output_dir
    )
    print(f"Completed in {elapsed} ms")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
