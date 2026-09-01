"""Pull referral documents, convert to markdown, and chunk to disk.

Atlas trace:
  DO: DO-58BD2EA0
  DI: DI-ACA9659D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-58BD2EA0")

Read-only against whichever Neo4j NEO4J_URI points at. Never writes
to Neo4j. Use the seed script to load chunks into a local graph.

Usage:
    python scripts/pull_and_chunk_referral.py --referral-id 000481914514
    python scripts/pull_and_chunk_referral.py --patient-id p1 --deid
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Any

import httpx

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.chunking.converter_client import (  # noqa: E402
    ConverterError,
    converter_path,
    needs_conversion,
    parse_markdown_response,
)
from libs.chunking.referral_document_prep import (  # noqa: E402
    build_leo_chunk_records,
    chunk_markdown_text,
)
from libs.chunking.validation_bundle import (  # noqa: E402
    deidentify_chunk_records,
    write_bundle,
)

_FIND_REFERRALS_FOR_PATIENT = """
MATCH (rr:ReferralRequest)-[:FOR_PATIENT]->(p:Patient)
WHERE toString(p.id) = $patient_id
RETURN toString(rr.id) AS referral_id
ORDER BY referral_id
"""

_FIND_PATIENT_FOR_REFERRAL = """
MATCH (rr:ReferralRequest {id: $referral_id})-[:FOR_PATIENT]->(p:Patient)
RETURN toString(p.id) AS patient_id
LIMIT 1
"""

_FIND_DOCUMENTS = """
MATCH (rr:ReferralRequest {id: $referral_id})-[:HAS_DOCUMENT]->(dr:DocumentReference)
RETURN toString(dr.id) AS doc_id,
       coalesce(dr.url, '') AS url,
       coalesce(dr.leoOriginalUrl, '') AS leo_original_url,
       coalesce(dr.leoPdfUrl, '') AS leo_pdf_url,
       coalesce(dr.contentType, '') AS content_type,
       coalesce(dr.documentTitle, dr.title, '') AS title
ORDER BY title
"""


def resolve_referral_ids(
    client: Any,
    *,
    patient_id: str | None = None,
    referral_id: str | None = None,
) -> list[str]:
    """Return referral ids from an explicit id or a patient lookup."""
    if referral_id:
        return [str(referral_id)]
    if not patient_id:
        raise ValueError("Provide --patient-id or --referral-id.")
    rows = client.run(_FIND_REFERRALS_FOR_PATIENT, patient_id=str(patient_id))
    return [str(row["referral_id"]) for row in rows if row.get("referral_id")]


def list_documents(client: Any, referral_id: str) -> list[dict[str, Any]]:
    """Return DocumentReference rows linked to a referral."""
    return client.run(_FIND_DOCUMENTS, referral_id=str(referral_id))


def fetch_url_for_document(doc: dict[str, Any]) -> str:
    """Prefer a signed blob URL over a FHIR Binary path."""
    for key in ("leo_original_url", "leo_pdf_url", "url"):
        value = str(doc.get(key) or "").strip()
        if value.startswith("http://") or value.startswith("https://"):
            return value
    return ""


def _patient_id_for_referral(client: Any, referral_id: str) -> str:
    rows = client.run(_FIND_PATIENT_FOR_REFERRAL, referral_id=str(referral_id))
    if not rows:
        return ""
    return str(rows[0].get("patient_id") or "")


def _fetch_binary(url: str) -> bytes:
    from libs.patient_documents.blob_url_signer import sign_patient_document_url

    signed = sign_patient_document_url(url) or url
    with httpx.Client(timeout=60.0, follow_redirects=True) as http:
        response = http.get(signed)
        response.raise_for_status()
        return response.content


def _to_markdown(
    content: bytes,
    *,
    filename: str,
    content_type: str,
    converter_url: str,
) -> str:
    if not needs_conversion(content_type):
        return content.decode("utf-8", errors="replace")
    path = converter_path(content_type)
    url = converter_url.rstrip("/") + path
    files = {
        "file": (
            filename or "document.bin",
            content,
            content_type or "application/octet-stream",
        )
    }
    with httpx.Client(timeout=120.0) as http:
        response = http.post(url, files=files)
        response.raise_for_status()
        return parse_markdown_response(response.json())


def _chunk_document(doc_id: str, markdown: str) -> list[dict[str, Any]]:
    return build_leo_chunk_records(doc_id, chunk_markdown_text(markdown))


def _process_document(
    doc: dict[str, Any],
    converter_url: str,
) -> list[dict[str, Any]]:
    url = fetch_url_for_document(doc)
    doc_id = str(doc.get("doc_id") or "")
    title = str(doc.get("title") or doc_id)
    content_type = str(doc.get("content_type") or "")
    if not url or not doc_id:
        print(f"  skip {doc_id or title}: missing fetchable url or id")
        return []
    print(f"  fetch {doc_id} ({content_type or 'unknown'})")
    content = _fetch_binary(url)
    try:
        markdown = _to_markdown(
            content,
            filename=title,
            content_type=content_type,
            converter_url=converter_url,
        )
    except (ConverterError, httpx.HTTPError) as exc:
        print(f"  skip {doc_id}: {exc}")
        return []
    records = _chunk_document(doc_id, markdown)
    print(f"  chunks {doc_id}: {len(records)}")
    return records


def pull_referral(
    client: Any,
    referral_id: str,
    *,
    output_dir: pathlib.Path,
    converter_url: str,
    deid: bool,
) -> pathlib.Path:
    """Pull one referral's documents and write a disk bundle."""
    patient_id = _patient_id_for_referral(client, referral_id)
    docs = list_documents(client, referral_id)
    chunks: list[dict[str, Any]] = []
    for doc in docs:
        chunks.extend(_process_document(doc, converter_url))
    chunks_deid = deidentify_chunk_records(chunks) if deid else None
    return write_bundle(
        output_dir,
        referral_id=referral_id,
        manifest={
            "patient_id": patient_id,
            "referral_id": referral_id,
            "doc_count": len(docs),
            "chunk_count": len(chunks),
            "deid": deid,
        },
        chunks=chunks,
        chunks_deid=chunks_deid,
    )


def _load_env() -> None:
    from dotenv import load_dotenv

    for name in ("secrets/.env", "secrets/.env.secrets", ".env"):
        load_dotenv(ROOT / name, override=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient-id")
    parser.add_argument("--referral-id")
    parser.add_argument("--output-dir", default="./output/chunks")
    parser.add_argument("--converter-url", default="http://localhost:8012")
    parser.add_argument("--deid", action="store_true")
    args = parser.parse_args()

    _load_env()
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    try:
        referral_ids = resolve_referral_ids(
            client,
            patient_id=args.patient_id,
            referral_id=args.referral_id,
        )
        if not referral_ids:
            print("No ReferralRequest found.")
            return 1
        output_dir = pathlib.Path(args.output_dir)
        for referral_id in referral_ids:
            print(f"referral {referral_id}")
            dest = pull_referral(
                client,
                referral_id,
                output_dir=output_dir,
                converter_url=args.converter_url,
                deid=args.deid,
            )
            print(f"wrote {dest}")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
