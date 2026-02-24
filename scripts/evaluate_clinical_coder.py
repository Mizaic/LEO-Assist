"""Run baseline vs hybrid clinical coder evaluation and compare reports."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger("evaluate_clinical_coder")
DEFAULT_INPUT = (
    ROOT
    / "services"
    / "terminology"
    / "data"
    / "training"
    / "surface_forms_4202301609.jsonl"
)
DEFAULT_OUT_DIR = ROOT / "services" / "terminology" / "data" / "training"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--use-llm-fallback", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )


def _run_prototype(
    mode: str,
    input_path: Path,
    out_jsonl: Path,
    report_json: Path,
    low_conf_jsonl: Path,
    limit: int | None,
    use_llm_fallback: bool,
) -> None:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "prototype_clinical_coder.py"),
        "--mode",
        mode,
        "--input",
        str(input_path),
        "--output",
        str(out_jsonl),
        "--report",
        str(report_json),
        "--low-confidence-output",
        str(low_conf_jsonl),
    ]
    if limit is not None:
        cmd += ["--limit", str(limit)]
    if use_llm_fallback:
        cmd.append("--use-llm-fallback")
    LOGGER.info("Running %s mode", mode)
    LOGGER.info("Command: %s", " ".join(cmd))
    started = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print(f"[{mode}] {line.rstrip()}", flush=True)
    rc = proc.wait()
    if rc != 0:
        raise subprocess.CalledProcessError(rc, cmd)
    LOGGER.info("%s mode completed in %.1fs", mode, time.monotonic() - started)


def _load_report(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _safe_delta(a: float, b: float) -> float:
    return round(b - a, 4)


def main() -> None:
    args = parse_args()
    _configure_logging(args.verbose)
    run_started = time.monotonic()
    LOGGER.info("Starting evaluation run input=%s", args.input)
    LOGGER.info("LLM fallback enabled for third pass: %s", args.use_llm_fallback)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    baseline_out = args.out_dir / "surface_forms.eval.lexical.jsonl"
    baseline_report = args.out_dir / "surface_forms.eval.lexical.report.json"
    baseline_low = args.out_dir / "surface_forms.eval.lexical.low_conf.jsonl"

    hybrid_out = args.out_dir / "surface_forms.eval.hybrid.jsonl"
    hybrid_report = args.out_dir / "surface_forms.eval.hybrid.report.json"
    hybrid_low = args.out_dir / "surface_forms.eval.hybrid.low_conf.jsonl"

    hybrid_llm_out = args.out_dir / "surface_forms.eval.hybrid_llm.jsonl"
    hybrid_llm_report = args.out_dir / "surface_forms.eval.hybrid_llm.report.json"
    hybrid_llm_low = args.out_dir / "surface_forms.eval.hybrid_llm.low_conf.jsonl"

    _run_prototype(
        mode="lexical",
        input_path=args.input,
        out_jsonl=baseline_out,
        report_json=baseline_report,
        low_conf_jsonl=baseline_low,
        limit=args.limit,
        use_llm_fallback=False,
    )
    _run_prototype(
        mode="hybrid",
        input_path=args.input,
        out_jsonl=hybrid_out,
        report_json=hybrid_report,
        low_conf_jsonl=hybrid_low,
        limit=args.limit,
        use_llm_fallback=False,
    )
    if args.use_llm_fallback:
        _run_prototype(
            mode="hybrid",
            input_path=args.input,
            out_jsonl=hybrid_llm_out,
            report_json=hybrid_llm_report,
            low_conf_jsonl=hybrid_llm_low,
            limit=args.limit,
            use_llm_fallback=True,
        )

    lexical = _load_report(baseline_report)
    hybrid = _load_report(hybrid_report)
    summary = {
        "input": str(args.input),
        "runs": {
            "lexical_report": str(baseline_report),
            "hybrid_report": str(hybrid_report),
        },
        "lexical_vs_hybrid": {
            "mapped_entities_delta": _safe_delta(
                float(lexical.get("mapped_entities", 0)),
                float(hybrid.get("mapped_entities", 0)),
            ),
            "no_candidate_delta": _safe_delta(
                float(lexical.get("no_candidate", 0)),
                float(hybrid.get("no_candidate", 0)),
            ),
            "high_conf_delta": _safe_delta(
                float(lexical.get("high_conf", 0)),
                float(hybrid.get("high_conf", 0)),
            ),
            "hitl_required_delta": _safe_delta(
                float(lexical.get("hitl_required", 0)),
                float(hybrid.get("hitl_required", 0)),
            ),
            "read_map_hit_rate_delta": _safe_delta(
                float(lexical.get("read_map_hit_rate", 0.0)),
                float(hybrid.get("read_map_hit_rate", 0.0)),
            ),
        },
    }

    if args.use_llm_fallback:
        hybrid_llm = _load_report(hybrid_llm_report)
        summary["runs"]["hybrid_llm_report"] = str(hybrid_llm_report)
        summary["hybrid_vs_hybrid_llm"] = {
            "llm_invoked": hybrid_llm.get("llm_invoked", 0),
            "llm_accepted": hybrid_llm.get("llm_accepted", 0),
            "hitl_required_delta": _safe_delta(
                float(hybrid.get("hitl_required", 0)),
                float(hybrid_llm.get("hitl_required", 0)),
            ),
        }

    compare_path = args.out_dir / "surface_forms.eval.compare.json"
    with compare_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    LOGGER.info("Evaluation complete in %.1fs", time.monotonic() - run_started)
    LOGGER.info("Comparison report: %s", compare_path)
    print("Evaluation complete.", flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    print(f"Comparison report: {compare_path}", flush=True)


if __name__ == "__main__":
    main()
