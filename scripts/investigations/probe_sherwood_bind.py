"""Read-only probe: does the Sherwood taught form bind, and does its text survive?

Runs the real bind-and-normalise path against the production patient graph
for one referral. Makes no writes and calls no LLM.

Usage:
    .venv/bin/python scripts/investigations/probe_sherwood_bind.py \
        --referral-id 000481914514
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / ".env", override=False)

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402
from libs.patient_document_runs.chunk_resolver import (  # noqa: E402
    resolve_pipeline_chunks,
)
from libs.pipeline.document_chunk_loader import bundle_fingerprint  # noqa: E402
from libs.pipeline.form_schema_normalizer import (  # noqa: E402
    normalise_chunks_with_schema,
)
from libs.pipeline.form_schema_store import (  # noqa: E402
    resolve_form_schema_traced,
)

_FIND_TARGET = """
MATCH (rr:ReferralRequest {id: $referral_id})-[:FOR_PATIENT]->(p:Patient)
OPTIONAL MATCH (rr)-[:FOR_SERVICE]->(sv:Service)
OPTIONAL MATCH (sv)<-[:PROVIDES_SERVICE]-(o:Organization)
OPTIONAL MATCH (rr)-[:HAS_DOCUMENT]->(dr:DocumentReference)
RETURN p.id AS patient_id, sv.id AS service_id, sv.name AS service_name,
       o.id AS org_id, o.name AS org_name,
       collect(DISTINCT dr.id) AS doc_ids
"""


def _resolve_target(client: PatientGraphClient, referral_id: str) -> dict:
    rows = client.run(_FIND_TARGET, referral_id=referral_id)
    if not rows:
        raise SystemExit(f"No ReferralRequest {referral_id!r} found.")
    return dict(rows[0])


def _section_c_len(text: str) -> int:
    """Characters after the Section C marker, 0 when the marker is absent."""
    lowered = text.lower()
    idx = lowered.find("section c")
    return 0 if idx < 0 else len(text) - idx


def _report_scope(target: dict, referral_id: str) -> tuple[str, str]:
    print(f"referral      : {referral_id}")
    print(f"patient       : {target.get('patient_id')}")
    print(f"service       : {target.get('service_id')} {target.get('service_name')!r}")
    print(f"organization  : {target.get('org_id')} {target.get('org_name')!r}")
    return str(target.get("org_id") or ""), str(target.get("service_id") or "")


def _report_bind(raw_texts: list[str], org_id: str, service_id: str):
    fingerprint = bundle_fingerprint(raw_texts)
    print(f"\nbundle fingerprint : {fingerprint}")

    client = PatientGraphClient()
    try:
        schema, match, loaded_key, label = resolve_form_schema_traced(
            client, fingerprint, organization_id=org_id, service_id=service_id
        )
    finally:
        client.close()

    print(f"match              : {match}")
    print(f"loaded_key         : {loaded_key}")
    print(f"label              : {label!r}")
    if schema is None:
        print("\nRESULT: no taught schema bound. Extraction runs generic rules.")
        return None
    print(f"sections           : {len(schema.sections)}")
    print(f"chunk_section_map  : {schema.chunk_section_map!r}")
    return schema


def _report_normalisation(schema, raw_texts: list[str]) -> None:
    normalised = normalise_chunks_with_schema(
        schema, raw_texts, schema.chunk_section_map
    )
    print("\nper-chunk character counts (raw -> normalised):")
    total_raw = total_norm = 0
    for i, (raw, norm) in enumerate(zip(raw_texts, normalised)):
        total_raw += len(raw)
        total_norm += len(norm)
        delta = len(norm) - len(raw)
        flag = "  <-- LOST TEXT" if delta < 0 else ""
        print(f"  chunk {i:>2}: {len(raw):>6} -> {len(norm):>6} ({delta:+d}){flag}")
        c_raw, c_norm = _section_c_len(raw), _section_c_len(norm)
        if c_raw or c_norm:
            print(f"            section C tail: {c_raw} -> {c_norm}")
    print(f"\n  TOTAL   : {total_raw} -> {total_norm} ({total_norm - total_raw:+d})")
    if "[NON_EXTRACTABLE]" in "".join(normalised):
        count = "".join(normalised).count("[NON_EXTRACTABLE]")
        print(f"  WARNING : {count} [NON_EXTRACTABLE] tokens in normalised text")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--referral-id", required=True)
    args = parser.parse_args()

    client = PatientGraphClient()
    try:
        target = _resolve_target(client, args.referral_id)
        org_id, service_id = _report_scope(target, args.referral_id)

        doc_ids = [d for d in (target.get("doc_ids") or []) if d]
        print(f"documents     : {doc_ids}")
        if not doc_ids:
            raise SystemExit("Referral has no DocumentReference.")

        resolved = None
        for doc_id in doc_ids:
            candidate = resolve_pipeline_chunks(
                client,
                document_reference_id=doc_id,
                referral_id=args.referral_id,
                backfill_legacy_ids=True,
            )
            print(
                f"  {doc_id}: {len(candidate.chunks)} chunks "
                f"(resolution={candidate.resolution})"
            )
            if candidate.chunks and resolved is None:
                resolved = candidate
    finally:
        client.close()

    if resolved is None:
        raise SystemExit("No document produced chunks.")

    raw_texts = [str(c.get("text") or "") for c in resolved.chunks]
    schema = _report_bind(raw_texts, org_id, service_id)
    if schema is not None and schema.sections:
        _report_normalisation(schema, raw_texts)


if __name__ == "__main__":
    main()
