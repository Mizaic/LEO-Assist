"""Recognise which taught form each document in a referral is -- locally.

Markdown in, one result per document out, with the evidence. No pipeline
runs and nothing is ever written anywhere.

Usage:
    python scripts/recognise_form.py --file referral.md
    python scripts/recognise_form.py --chunks chunks.json --json
    python scripts/recognise_form.py --file f.md --templates tests/fixtures/form_schema
    python scripts/recognise_form.py --file f.md --from-graph --organization-id RK5

``--chunks`` takes a JSON list of chunk strings, or ``{"chunks": [...]}``
where each chunk is a string or ``{"text": ...}``. ``--from-graph`` reads
the taught forms from the patient graph in a read-only session and prints
NEO4J_URI first, so you always know which graph you are reading.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from neo4j import READ_ACCESS, GraphDatabase  # noqa: E402

from libs.form_recognition.recogniser import (  # noqa: E402
    NotAForm,
    RecognitionFailed,
    Recognised,
    bundle_needs_review,
    recognise_bundle,
)
from libs.form_recognition.schema_files import load_schema_dir  # noqa: E402
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402
from libs.pipeline.form_schema_candidates import load_candidate_schemas  # noqa: E402
from libs.pipeline.form_schema_normalizer import FormSchema  # noqa: E402
from libs.pipeline.form_schema_store import FormSchemaLookupError  # noqa: E402

DEFAULT_TEMPLATES = ROOT / "tests" / "fixtures" / "form_schema"
_WRITE_CLAUSE_RE = re.compile(
    r"\b(?:MERGE|CREATE|SET|DELETE|DETACH|REMOVE|DROP|CALL|FOREACH|LOAD\s+CSV)\b",
    re.IGNORECASE,
)
_MAX_LISTED = 8


def assert_read_only(query: str) -> None:
    """Refuse any Cypher that could write. This harness only ever reads."""
    match = _WRITE_CLAUSE_RE.search(query or "")
    if match:
        raise ValueError(f"Refusing to run Cypher with {match.group(0)!r}")


class ReadOnlyGraph:
    """A patient-graph connection that can only run read transactions."""

    def __init__(self, driver: Any) -> None:
        self._driver = driver

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        assert_read_only(query)
        with self._driver.session(default_access_mode=READ_ACCESS) as session:
            return session.execute_read(
                lambda tx: [record.data() for record in tx.run(query, **params)]
            )

    def close(self) -> None:
        self._driver.close()


def _graph_uri() -> str:
    return os.getenv("NEO4J_URI", "") or os.getenv("NEO4J_PATIENT_URI", "")


def open_read_only_graph() -> ReadOnlyGraph:
    """Connect to the graph NEO4J_URI names, for reading only."""
    user = os.getenv("NEO4J_USER") or os.getenv("NEO4J_PATIENT_USER") or "neo4j"
    password = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PATIENT_PASSWORD")
    if not _graph_uri() or not password:
        raise SystemExit("NEO4J_URI and NEO4J_PASSWORD must be set for --from-graph")
    return ReadOnlyGraph(GraphDatabase.driver(_graph_uri(), auth=(user, password)))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="A markdown form or bundle")
    source.add_argument("--chunks", type=Path, help="A JSON list of stored chunks")
    parser.add_argument("--templates", type=Path, default=DEFAULT_TEMPLATES)
    parser.add_argument("--from-graph", action="store_true")
    parser.add_argument("--organization-id", default="")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    return parser.parse_args(argv)


def _chunk_text(chunk: Any) -> str:
    return chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)


def read_chunks(args: argparse.Namespace) -> list[str]:
    """Return the chunks to score, from --file or --chunks."""
    if args.file is not None:
        return [args.file.read_text(encoding="utf-8")]
    payload = json.loads(args.chunks.read_text(encoding="utf-8"))
    raw = payload.get("chunks", []) if isinstance(payload, dict) else payload
    return [_chunk_text(chunk) for chunk in raw]


def load_schemas(args: argparse.Namespace) -> list[FormSchema]:
    """Return candidate forms from the templates folder or the graph."""
    if not args.from_graph:
        return load_schema_dir(args.templates)
    load_keyvault_secrets()
    print(f"NEO4J_URI: {_graph_uri()}", flush=True)
    graph = open_read_only_graph()
    try:
        return load_candidate_schemas(graph, args.organization_id)
    finally:
        graph.close()


def _names(labels: tuple[str, ...]) -> str:
    shown = "; ".join(labels[:_MAX_LISTED])
    extra = len(labels) - _MAX_LISTED
    return f"{shown} (+{extra} more)" if extra > 0 else shown


def _evidence_lines(outcome: Any) -> list[str]:
    best = getattr(outcome, "best", None)
    if best is None:
        return []
    total = len(best.matched) + len(best.missing)
    label = "Matched form" if isinstance(outcome, Recognised) else "Closest form"
    lines = [
        f"  {label}: {best.form_name} ({best.fingerprint})",
        f"  Found {len(best.matched)} of {total} taught headings and options. "
        f"recall={best.recall:.2f} precision={best.precision:.2f} "
        f"order={best.order:.2f} options={best.option_coverage:.2f}",
    ]
    if best.missing:
        lines.append(f"  Missing: {_names(best.missing)}")
    if best.unexplained:
        lines.append(f"  Not explained by this form: {_names(best.unexplained)}")
    runner_up = getattr(outcome, "runner_up", None)
    if runner_up is not None:
        lines.append(
            f"  Runner-up: {runner_up.form_name} (recall {runner_up.recall:.2f})"
        )
    return lines


def _headline(outcome: Any) -> str:
    if isinstance(outcome, Recognised):
        return f"  Recognised as {outcome.schema.form_name}."
    if isinstance(outcome, NotAForm):
        return "  Not a form. It reads like a letter, so the generic path applies."
    if isinstance(outcome, RecognitionFailed):
        return f"  We could not score this document: {outcome.error}"
    return "  Not recognised. It looks like a form, but no taught form matches."


def print_text(results: list[Any]) -> None:
    for number, outcome in enumerate(results, start=1):
        print(f"Document {number}: {outcome.title or '(untitled)'}")
        print(_headline(outcome))
        for line in _evidence_lines(outcome):
            print(line)
    if bundle_needs_review(results):
        print("Result: A person needs to review this referral.")
    else:
        print("Result: Every form-like document was recognised.")


def _report(args: argparse.Namespace, results: list[Any]) -> dict[str, Any]:
    return {
        "source": "graph" if args.from_graph else "templates",
        "templates": "" if args.from_graph else str(args.templates),
        "organization_id": args.organization_id,
        "documents": [outcome.to_dict() for outcome in results],
        "needs_review": bundle_needs_review(results),
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        schemas = load_schemas(args)
    except FormSchemaLookupError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    results = recognise_bundle(read_chunks(args), schemas)
    if args.json:
        print(json.dumps(_report(args, results), indent=2, ensure_ascii=True))
    else:
        print_text(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
