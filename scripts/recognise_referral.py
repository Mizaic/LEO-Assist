"""Score one unprepared referral from its blob, on disk only.

Reads the blob URL from Neo4j, converts through the doc converter, chunks
the markdown locally, and scores each document. Never writes to Neo4j.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import types
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

import httpx
from azure.storage.blob import BlobClient

from libs.chunking.referral_document_prep import (
    build_leo_chunk_records,
    chunk_markdown_text,
)
from libs.chunking.validation_bundle import load_bundle, write_bundle
from libs.form_recognition.recogniser import (
    NotAForm,
    Recognised,
    recognise_document,
)
from libs.form_recognition.scoring import Score
from libs.form_recognition.settings import (
    MARGIN_MIN,
    MAX_UNEXPLAINED,
    OPTION_COVERAGE_MIN,
    ORDER_MIN,
    PRECISION_MIN,
    RECALL_MIN,
)
from libs.patient_documents.blob_url_signer import (
    _parse_blob_url,
    sign_patient_document_url,
)
from libs.pipeline.form_schema_normalizer import FormSchema
from scripts.build_form_recognition_fixtures import load_parser
from scripts.pull_and_chunk_referral import fetch_url_for_document

LOCAL_SECRETS = Path(__file__).resolve().parents[1] / "secrets" / ".env.secrets"
STORAGE_KEY_PREFIX = "PATIENT_DOCUMENT_"
PDF_READER_REL = Path("agent") / "leo_agents" / "services" / "pdf_to_markdown.py"
PDF_CONTENT_TYPE = "application/pdf"

FIND_REFERRAL = """
MATCH (rr:ReferralRequest {id: $referral_id})
OPTIONAL MATCH (rr)-[:FOR_SERVICE]->(direct:Service)
OPTIONAL MATCH (rr)-[:IN_WORKFLOW]->(:Workflow)-[:FOR_SERVICE]->(routed:Service)
WITH rr, coalesce(direct, routed) AS svc
OPTIONAL MATCH (svc)-[:PROVIDES_SERVICE_FOR]->(org:Organization)
RETURN coalesce(org.id, rr.organization_id, '') AS organization_id,
       coalesce(org.name, '') AS organization_name,
       coalesce(toString(svc.id), rr.service_id, '') AS service_id,
       coalesce(svc.name, '') AS service_name
LIMIT 1
"""

FIND_DOCUMENTS = """
MATCH (rr:ReferralRequest {id: $referral_id})-[:HAS_DOCUMENT]->(dr:DocumentReference)
RETURN toString(dr.id) AS doc_id,
       coalesce(dr.documentTitle, dr.title, '') AS title,
       coalesce(dr.contentType, '') AS content_type,
       coalesce(dr.leoOriginalUrl, '') AS leo_original_url,
       coalesce(dr.leoPdfUrl, '') AS leo_pdf_url,
       coalesce(dr.url, '') AS url
ORDER BY title
"""

Fetch = Callable[[str], bytes]
ToHtml = Callable[[bytes, str, str], str]
ToMarkdown = Callable[[str], str]
PdfToMarkdown = Callable[[bytes, str], str]


@dataclass(frozen=True)
class ReferralDocument:
    """One DocumentReference that still needs converting."""

    doc_id: str
    title: str
    content_type: str
    url: str


@dataclass(frozen=True)
class ReferralContext:
    """The referral facts the probe is allowed to read."""

    organization_id: str
    organization_name: str
    service_id: str
    service_name: str
    documents: tuple[ReferralDocument, ...]


def load_referral_context(graph: Any, referral_id: str) -> ReferralContext | None:
    """Read one referral's organisation, service, and document blob URLs."""
    rows = graph.run(FIND_REFERRAL, referral_id=referral_id)
    if not rows:
        return None
    row = rows[0]
    documents = tuple(
        ReferralDocument(
            doc_id=str(doc.get("doc_id") or ""),
            title=str(doc.get("title") or ""),
            content_type=str(doc.get("content_type") or ""),
            url=fetch_url_for_document(doc),
        )
        for doc in graph.run(FIND_DOCUMENTS, referral_id=referral_id)
        if doc.get("doc_id")
    )
    return ReferralContext(
        organization_id=str(row.get("organization_id") or ""),
        organization_name=str(row.get("organization_name") or ""),
        service_id=str(row.get("service_id") or ""),
        service_name=str(row.get("service_name") or ""),
        documents=documents,
    )


def failed_gates(best: Score | None, runner_up: Score | None) -> list[str]:
    """Name each recognition gate the best form missed."""
    if best is None:
        return []
    failed: list[str] = []
    if best.recall < RECALL_MIN:
        failed.append("recall")
    if best.option_coverage < OPTION_COVERAGE_MIN:
        failed.append("options")
    if best.order < ORDER_MIN:
        failed.append("order")
    if len(best.unexplained) > MAX_UNEXPLAINED and best.precision < PRECISION_MIN:
        failed.append("precision")
    if runner_up is not None and best.recall - runner_up.recall < MARGIN_MIN:
        failed.append("margin")
    return failed


def _decision_line(row: dict[str, Any]) -> str:
    outcome = row["outcome"]
    if outcome == "not_scored":
        return "pause. The file was not converted."
    if outcome == "recognition_failed":
        return "pause. Scoring failed."
    if outcome == "unrecognised":
        return "pause. A person needs to teach this form."
    if row["decision"] == "generic_letter":
        return "generic letter path. Do not pause."
    return "use this schema. Do not pause."


def _status(row: dict[str, Any]) -> str:
    names = {
        "recognised": "recognised",
        "unrecognised": "not recognised",
        "not_a_form": "not a form",
        "recognition_failed": "not scored",
        "not_scored": "not scored",
    }
    return names.get(str(row["outcome"]), str(row["outcome"]))


def _form_line(row: dict[str, Any]) -> str:
    best = (row.get("recognition") or {}).get("best")
    if not best or row["outcome"] not in ("recognised", "unrecognised"):
        return ""
    label = "Form" if row["outcome"] == "recognised" else "Closest form"
    return (
        f"  {label}: {best['form_name']} ({best['fingerprint']}) "
        f"recall {best['recall']:.2f} precision {best['precision']:.2f}"
    )


def print_referral(graph_uri: str, report: dict[str, Any]) -> None:
    """Print one referral report. UBRN and document ids only."""
    print(f"NEO4J_URI: {graph_uri}")
    print(f"UBRN {report['referral_id']}")
    org = report["organization_id"] or "(none)"
    service = report["service_name"] or "(none)"
    print(f"Organisation: {org}  Service: {service}")
    print(f"Documents on this referral: {len(report['documents'])}")
    print()
    for row in report["documents"]:
        title = row["title"] or "(untitled)"
        print(f"{row['doc_id']}  {title}")
        print(f"  Status: {_status(row)}")
        print(f"  Decision: {_decision_line(row)}")
        form = _form_line(row)
        if form:
            print(form)
        if row["failed_gates"]:
            print(f"  Failed gates: {', '.join(row['failed_gates'])}")
        if row["error"]:
            print(f"  Error: {row['error']}")
    if report["needs_review"]:
        print("Referral decision: pause")
        return
    print("Referral decision: continue")


def run_referral(
    referral_id: str,
    *,
    graph_uri: str,
    context: ReferralContext | None,
    schemas: list[FormSchema],
    output_dir: Path,
    fetch: Fetch,
    to_html: ToHtml,
    to_markdown: ToMarkdown,
    pdf_to_markdown: PdfToMarkdown | None = None,
    bundle_dir: Path | None = None,
) -> int:
    """Print the report for one referral. Returns 0, or 1 if it is missing."""
    if context is None:
        print(f"NEO4J_URI: {graph_uri}")
        print(f"UBRN {referral_id} was not found.")
        return 1
    report = probe_referral(
        referral_id,
        context,
        schemas,
        output_dir=output_dir,
        fetch=fetch,
        to_html=to_html,
        to_markdown=to_markdown,
        pdf_to_markdown=pdf_to_markdown,
        bundle_dir=bundle_dir,
    )
    print_referral(graph_uri, report)
    return 0


def _decision(outcome: Any) -> str:
    if isinstance(outcome, Recognised):
        return "use_schema"
    if isinstance(outcome, NotAForm):
        return "generic_letter"
    return "pause"


def _scored_row(doc: ReferralDocument, outcome: Any) -> dict[str, Any]:
    return {
        "doc_id": doc.doc_id,
        "title": doc.title,
        "outcome": outcome.kind,
        "decision": _decision(outcome),
        "failed_gates": failed_gates(outcome.best, outcome.runner_up),
        "recognition": outcome.to_dict(),
        "error": "",
    }


def _not_scored(doc: ReferralDocument, error: str) -> dict[str, Any]:
    return {
        "doc_id": doc.doc_id,
        "title": doc.title,
        "outcome": "not_scored",
        "decision": "pause",
        "failed_gates": [],
        "recognition": None,
        "error": error,
    }


@dataclass(frozen=True)
class _Converters:
    fetch: Fetch
    to_html: ToHtml
    to_markdown: ToMarkdown
    pdf_to_markdown: PdfToMarkdown | None


class NoPdfReaderError(RuntimeError):
    """A PDF reached the probe but no PDF reader was loaded."""


def is_pdf(doc: ReferralDocument) -> bool:
    """Match production: PDFs and eRS clinical information skip the converter."""
    return (
        doc.content_type.lower() == PDF_CONTENT_TYPE
        or "clinical-information" in doc.doc_id
    )


def _to_markdown(doc: ReferralDocument, convert: _Converters) -> str:
    content = convert.fetch(doc.url)
    filename = doc.title or doc.doc_id
    if not is_pdf(doc):
        html = convert.to_html(content, filename, doc.content_type)
        return convert.to_markdown(html)
    if convert.pdf_to_markdown is None:
        raise NoPdfReaderError(
            "No PDF reader is loaded. Install pdfplumber, then try again."
        )
    return convert.pdf_to_markdown(content, filename)


def _convert_one(
    doc: ReferralDocument,
    schemas: list[FormSchema],
    convert: _Converters,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not doc.url:
        return _not_scored(doc, "No blob URL on this document."), []
    try:
        markdown = _to_markdown(doc, convert)
    except NoPdfReaderError as exc:
        return _not_scored(doc, str(exc)), []
    except Exception as exc:  # a missed file must stay on the report
        return _not_scored(doc, f"{type(exc).__name__}: {exc}"), []
    if not (markdown or "").strip():
        return _not_scored(doc, "Conversion returned empty markdown."), []
    records = build_leo_chunk_records(doc.doc_id, chunk_markdown_text(markdown))
    outcome = replace(recognise_document(markdown, schemas), title=doc.title)
    return _scored_row(doc, outcome), records


def _texts_by_doc(chunks: list[dict[str, Any]]) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for chunk in chunks:
        doc_id = str(chunk.get("document_reference_id") or "")
        grouped.setdefault(doc_id, []).append(str(chunk.get("text") or ""))
    return {doc_id: "\n\n".join(parts) for doc_id, parts in grouped.items()}


def _report(
    referral_id: str,
    context: ReferralContext,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "referral_id": referral_id,
        "organization_id": context.organization_id,
        "organization_name": context.organization_name,
        "service_id": context.service_id,
        "service_name": context.service_name,
        "neo4j_write": False,
        "documents": rows,
        "needs_review": any(row["decision"] == "pause" for row in rows),
    }


def _probe_saved(
    referral_id: str,
    context: ReferralContext,
    schemas: list[FormSchema],
    bundle_dir: Path,
) -> dict[str, Any]:
    """Score markdown already stored in a disk bundle. Does not download."""
    bundle = load_bundle(bundle_dir)
    texts = _texts_by_doc(bundle.chunks)
    rows: list[dict[str, Any]] = []
    for saved in bundle.manifest.get("documents") or []:
        doc = ReferralDocument(
            doc_id=str(saved.get("doc_id") or ""),
            title=str(saved.get("title") or ""),
            content_type=str(saved.get("content_type") or ""),
            url="",
        )
        text = texts.get(doc.doc_id, "")
        if not text.strip():
            error = str(saved.get("error") or "No saved markdown for this document.")
            rows.append(_not_scored(doc, error))
            continue
        outcome = replace(recognise_document(text, schemas), title=doc.title)
        rows.append(_scored_row(doc, outcome))
    return _report(referral_id, context, rows)


def probe_referral(
    referral_id: str,
    context: ReferralContext,
    schemas: list[FormSchema],
    *,
    output_dir: Path,
    fetch: Fetch,
    to_html: ToHtml,
    to_markdown: ToMarkdown,
    pdf_to_markdown: PdfToMarkdown | None = None,
    bundle_dir: Path | None = None,
) -> dict[str, Any]:
    """Convert each document, score it, and write a disk bundle."""
    if bundle_dir is not None:
        return _probe_saved(referral_id, context, schemas, bundle_dir)
    convert = _Converters(fetch, to_html, to_markdown, pdf_to_markdown)
    rows: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    for doc in context.documents:
        row, records = _convert_one(doc, schemas, convert)
        rows.append(row)
        chunks.extend(records)
    write_bundle(
        output_dir,
        referral_id=referral_id,
        manifest={
            "organization_id": context.organization_id,
            "organization_name": context.organization_name,
            "service_id": context.service_id,
            "service_name": context.service_name,
            "neo4j_write": False,
            "documents": rows,
        },
        chunks=chunks,
    )
    return _report(referral_id, context, rows)


class BlobFetchError(RuntimeError):
    """The blob could not be downloaded."""


def post_convert_html(
    content: bytes,
    *,
    filename: str,
    content_type: str,
    converter_url: str,
) -> str:
    """Ask the doc converter for HTML. Markdown is a later step."""
    url = converter_url.rstrip("/") + "/convert"
    files = {
        "file": (
            filename or "document.bin",
            content,
            content_type or "application/octet-stream",
        )
    }
    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, data={"target_format": "html"}, files=files)
        response.raise_for_status()
        html = response.text.strip()
    if not html:
        raise RuntimeError("converter returned empty HTML")
    return html


def az_executable() -> str:
    """Return the Azure CLI program. On Windows that file is az.cmd."""
    for name in ("az.cmd", "az"):
        found = shutil.which(name)
        if found:
            return found
    raise BlobFetchError(
        "Azure CLI was not found. Install az and sign in, then try again."
    )


def az_download_args(url: str, dest: Path) -> list[str]:
    """Build an Azure CLI download for one blob URL. Uses the logged-in user."""
    parsed = _parse_blob_url(url)
    if parsed is None:
        raise BlobFetchError("Not an Azure blob URL")
    account, container, name = parsed
    return [
        "az",
        "storage",
        "blob",
        "download",
        "--account-name",
        account,
        "--container-name",
        container,
        "--name",
        name,
        "--auth-mode",
        "login",
        "--file",
        str(dest),
        "--only-show-errors",
    ]


def _http_get(url: str) -> bytes:
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def _az_download(url: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "blob"
        command = az_download_args(url, dest)
        command[0] = az_executable()
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0 or not dest.is_file():
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise BlobFetchError(detail or "az storage blob download failed")
        return dest.read_bytes()


def _account_name(connection_string: str) -> str:
    for part in connection_string.split(";"):
        if part.startswith("AccountName="):
            return part.split("=", 1)[1]
    return ""


def _connection_string_for_account(account: str) -> str:
    """Return a storage connection string for this account, read at call time."""
    names = (
        "PATIENT_DOCUMENT_STORAGE_CONNECTION_STRING",
        f"PATIENT_DOCUMENT_STORAGE_CONNECTION_STRING__{account}",
    )
    for name in names:
        value = os.getenv(name, "").strip()
        if value and _account_name(value) == account:
            return value
    extra = os.getenv("PATIENT_DOCUMENT_EXTRA_STORAGE_CONNECTION_STRINGS", "")
    for line in extra.splitlines():
        candidate = line.strip()
        if candidate and _account_name(candidate) == account:
            return candidate
    return ""


def _download_with_connection_string(url: str) -> bytes | None:
    parsed = _parse_blob_url(url)
    if parsed is None:
        return None
    account, container, name = parsed
    connection = _connection_string_for_account(account)
    if not connection:
        return None
    client = BlobClient.from_connection_string(
        connection, container_name=container, blob_name=name
    )
    return client.download_blob().readall()


def load_storage_keys(path: Path = LOCAL_SECRETS) -> int:
    """Load storage keys from the local secrets file. Never overrides the shell.

    Key Vault does not hold these keys, and secrets/.env.config turns Key
    Vault on, so the main loader skips this file.
    """
    if not path.is_file():
        return 0
    loaded = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = raw.strip().partition("=")
        key = key.strip()
        if not sep or not key.startswith(STORAGE_KEY_PREFIX) or key in os.environ:
            continue
        os.environ[key] = value.strip()
        loaded += 1
    return loaded


def _no_key_message(url: str, detail: str) -> str:
    account = _parse_blob_url(url)[0]
    return (
        f"No storage key for account {account}. Add "
        "PATIENT_DOCUMENT_STORAGE_CONNECTION_STRING for that account to "
        f"secrets/.env.secrets, then try again. Azure CLI also failed: {detail}"
    )


def download_blob(url: str) -> bytes:
    """Download a document with the storage key, then a signed URL, then az."""
    keyed = _download_with_connection_string(url)
    if keyed is not None:
        return keyed
    signed = sign_patient_document_url(url) or url
    try:
        return _http_get(signed)
    except Exception:
        if _parse_blob_url(url) is None:
            raise
    try:
        return _az_download(url)
    except BlobFetchError as exc:
        raise BlobFetchError(_no_key_message(url, str(exc))) from exc


def load_markdown_parser(agents_repo: Path) -> Any:
    """Load the HCCP-Agents HTML to markdown parser. Do not copy it."""
    return load_parser(Path(agents_repo))


def _stub_fhirpathpy() -> None:
    """pdf_to_markdown.py imports fhirpathpy but never calls it."""
    if importlib.util.find_spec("fhirpathpy") is not None:
        return
    module = types.ModuleType("fhirpathpy")
    module.evaluate = None
    sys.modules["fhirpathpy"] = module


def load_pdf_reader(agents_repo: Path) -> PdfToMarkdown:
    """Load the HCCP-Agents PDF to markdown reader. Do not copy it."""
    path = Path(agents_repo) / PDF_READER_REL
    if not path.is_file():
        raise SystemExit(f"HCCP-Agents PDF reader not found at {path}")
    _stub_fhirpathpy()
    spec = importlib.util.spec_from_file_location("hccp_pdf_to_markdown", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def read(content: bytes, filename: str) -> str:
        markdown, _name = module.process_pdf_to_markdown(content, filename)
        return markdown

    return read
