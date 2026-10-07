"""Single-UBRN form recognition: blob to markdown on disk, then score.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from libs.form_recognition.schema_files import load_schema_dir
from scripts.recognise_form import assert_read_only
from scripts.recognise_referral import (
    ReferralContext,
    ReferralDocument,
    load_referral_context,
    probe_referral,
    run_referral,
)
from tests.form_recognition_corpus import document_by_id

REPO = Path(__file__).resolve().parents[1]
DEVON = REPO / "tests" / "fixtures" / "form_recognition" / "schemas"
UBRN = "000481914514"
WORD = "application/vnd.openxmlformats-officedocument" ".wordprocessingml.document"


def test_probe_scores_converted_markdown_and_writes_a_bundle(tmp_path: Path) -> None:
    seen: dict[str, str] = {}

    def fetch(url: str) -> bytes:
        seen["url"] = url
        return b"docx-bytes"

    def to_html(content: bytes, filename: str, content_type: str) -> str:
        seen["filename"] = filename
        seen["content_type"] = content_type
        assert content == b"docx-bytes"
        return "<html>form</html>"

    def to_markdown(html: str) -> str:
        seen["html"] = html
        return document_by_id("devon-gynae-docx")

    context = ReferralContext(
        organization_id="RK5",
        organization_name="Example Trust",
        service_id="svc-1",
        service_name="Lower GI 2WW",
        documents=(
            ReferralDocument(
                doc_id="dr-19",
                title="Clinical information.docx",
                content_type=(
                    "application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"
                ),
                url="https://acct.blob.core.windows.net/letters/dr-19.docx",
            ),
        ),
    )
    report = probe_referral(
        UBRN,
        context,
        load_schema_dir(DEVON),
        output_dir=tmp_path,
        fetch=fetch,
        to_html=to_html,
        to_markdown=to_markdown,
    )

    (doc,) = report["documents"]
    assert doc["doc_id"] == "dr-19"
    assert doc["outcome"] == "recognised"
    assert doc["decision"] == "use_schema"
    assert doc["failed_gates"] == []
    assert report["needs_review"] is False
    assert report["neo4j_write"] is False
    assert seen["url"].endswith("dr-19.docx")
    assert seen["html"] == "<html>form</html>"
    bundle = tmp_path / UBRN / "chunks.json"
    assert bundle.is_file()
    assert "dr-19" in bundle.read_text(encoding="utf-8")


def _never_html(content: bytes, filename: str, content_type: str) -> str:
    raise AssertionError("a PDF must not go to the doc converter")


@pytest.mark.parametrize(
    ("doc_id", "content_type"),
    [
        ("dr-20", "application/pdf"),
        (f"{UBRN}-clinical-information", ""),
    ],
)
def test_pdf_is_read_by_the_pdf_reader_not_the_converter(
    tmp_path: Path, doc_id: str, content_type: str
) -> None:
    seen: dict[str, object] = {}

    def pdf_to_markdown(content: bytes, filename: str) -> str:
        seen["content"] = content
        seen["filename"] = filename
        return document_by_id("devon-gynae-docx")

    context = ReferralContext(
        organization_id="RK5",
        organization_name="Example Trust",
        service_id="svc-1",
        service_name="Lower GI 2WW",
        documents=(
            ReferralDocument(
                doc_id=doc_id,
                title="Clinical Information.pdf",
                content_type=content_type,
                url="https://acct.blob.core.windows.net/letters/info.pdf",
            ),
        ),
    )
    report = probe_referral(
        UBRN,
        context,
        load_schema_dir(DEVON),
        output_dir=tmp_path,
        fetch=lambda _url: b"%PDF-bytes",
        to_html=_never_html,
        to_markdown=lambda _html: "",
        pdf_to_markdown=pdf_to_markdown,
    )

    (doc,) = report["documents"]
    assert doc["outcome"] == "recognised"
    assert seen == {"content": b"%PDF-bytes", "filename": "Clinical Information.pdf"}


def test_pdf_with_no_pdf_reader_is_not_scored(tmp_path: Path) -> None:
    context = ReferralContext(
        organization_id="",
        organization_name="",
        service_id="",
        service_name="",
        documents=(
            ReferralDocument(
                doc_id="dr-20",
                title="Clinical Information.pdf",
                content_type="application/pdf",
                url="https://acct.blob.core.windows.net/letters/info.pdf",
            ),
        ),
    )
    report = probe_referral(
        UBRN,
        context,
        load_schema_dir(DEVON),
        output_dir=tmp_path,
        fetch=lambda _url: b"%PDF-bytes",
        to_html=_never_html,
        to_markdown=lambda _html: "",
    )

    (doc,) = report["documents"]
    assert doc["outcome"] == "not_scored"
    assert doc["decision"] == "pause"
    assert doc["error"].startswith("No PDF reader is loaded")


def test_pdf_reader_loads_from_the_agents_repo(tmp_path: Path) -> None:
    from scripts.recognise_referral import PDF_READER_REL, load_pdf_reader

    module = tmp_path / PDF_READER_REL
    module.parent.mkdir(parents=True)
    module.write_text(
        "from fhirpathpy import evaluate\n"
        "def process_pdf_to_markdown(pdf_bytes, original_filename):\n"
        "    return f'{original_filename}:{len(pdf_bytes)}', 'x.md'\n",
        encoding="utf-8",
    )

    reader = load_pdf_reader(tmp_path)

    assert reader(b"abc", "info.pdf") == "info.pdf:3"


def test_from_bundle_scores_saved_chunks_without_downloading(tmp_path: Path) -> None:
    markdown = document_by_id("devon-gynae-docx")
    context = ReferralContext(
        organization_id="RK5",
        organization_name="Example Trust",
        service_id="svc-1",
        service_name="Lower GI 2WW",
        documents=(
            ReferralDocument(
                doc_id="dr-19",
                title="Clinical information.docx",
                content_type=WORD,
                url="https://acct.blob.core.windows.net/letters/dr-19.docx",
            ),
        ),
    )

    def fetch(_url: str) -> bytes:
        return b"docx-bytes"

    def to_html(content: bytes, filename: str, content_type: str) -> str:
        del content, filename, content_type
        return "<html>form</html>"

    probe_referral(
        UBRN,
        context,
        load_schema_dir(DEVON),
        output_dir=tmp_path,
        fetch=fetch,
        to_html=to_html,
        to_markdown=lambda _html: markdown,
    )

    def fetch_again(_url: str) -> bytes:
        raise AssertionError("blob was downloaded on a retest")

    report = probe_referral(
        UBRN,
        context,
        load_schema_dir(DEVON),
        output_dir=tmp_path,
        fetch=fetch_again,
        to_html=to_html,
        to_markdown=lambda _html: markdown,
        bundle_dir=tmp_path / UBRN,
    )
    (doc,) = report["documents"]
    assert doc["outcome"] == "recognised"
    assert doc["decision"] == "use_schema"


class _Graph:
    def __init__(self, rows_by_marker: dict[str, list[dict]]) -> None:
        self.rows_by_marker = rows_by_marker
        self.queries: list[str] = []

    def run(self, query: str, **params: object) -> list[dict]:
        assert_read_only(query)
        assert params["referral_id"] == UBRN
        self.queries.append(query)
        for marker, rows in self.rows_by_marker.items():
            if marker in query:
                return rows
        return []


def test_referral_query_follows_the_live_service_to_organisation_link() -> None:
    from scripts.recognise_referral import FIND_REFERRAL

    assert "(svc)-[:PROVIDES_SERVICE_FOR]->(org:Organization)" in FIND_REFERRAL
    assert "-[:IN_WORKFLOW]->(:Workflow)-[:FOR_SERVICE]->" in FIND_REFERRAL
    assert "<-[:PROVIDES_SERVICE]-" not in FIND_REFERRAL


def test_load_referral_reads_the_blob_url_and_organisation() -> None:
    graph = _Graph(
        {
            "(svc)-[:PROVIDES_SERVICE_FOR]->(org:Organization)": [
                {
                    "organization_id": "RK5",
                    "organization_name": "Example Trust",
                    "service_id": "svc-1",
                    "service_name": "Lower GI 2WW",
                }
            ],
            "HAS_DOCUMENT": [
                {
                    "doc_id": "dr-19",
                    "title": "Clinical information.docx",
                    "content_type": WORD,
                    "leo_original_url": (
                        "https://acct.blob.core.windows.net/letters/dr-19.docx"
                    ),
                    "leo_pdf_url": "",
                    "url": "",
                }
            ],
        }
    )
    context = load_referral_context(graph, UBRN)
    assert context is not None
    assert context.organization_id == "RK5"
    assert context.service_name == "Lower GI 2WW"
    (doc,) = context.documents
    assert doc.doc_id == "dr-19"
    assert doc.url == "https://acct.blob.core.windows.net/letters/dr-19.docx"


def test_run_referral_prints_the_decision(capsys, tmp_path: Path) -> None:
    context = ReferralContext(
        organization_id="RK5",
        organization_name="Example Trust",
        service_id="svc-1",
        service_name="Lower GI 2WW",
        documents=(
            ReferralDocument(
                doc_id="dr-19",
                title="Clinical information.docx",
                content_type=WORD,
                url="https://acct.blob.core.windows.net/letters/dr-19.docx",
            ),
        ),
    )
    code = run_referral(
        UBRN,
        graph_uri="neo4j+s://graph.example",
        context=context,
        schemas=load_schema_dir(DEVON),
        output_dir=tmp_path,
        fetch=lambda _url: b"docx-bytes",
        to_html=lambda content, filename, content_type: "<html>form</html>",
        to_markdown=lambda _html: document_by_id("devon-gynae-docx"),
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "NEO4J_URI: neo4j+s://graph.example" in out
    assert "UBRN 000481914514" in out
    assert "dr-19" in out
    assert "Decision: use this schema. Do not pause." in out
    assert "neo4j_write" not in out


def _row(outcome: str, decision: str, best: dict | None) -> dict:
    return {
        "doc_id": f"dr-{outcome}",
        "title": "letter.doc",
        "outcome": outcome,
        "decision": decision,
        "failed_gates": [],
        "recognition": {"best": best},
        "error": "",
    }


def test_report_names_the_matched_form_and_the_closest_form(capsys) -> None:
    from scripts.recognise_referral import print_referral

    gynae = {
        "fingerprint": "sfh-gynae-2ww",
        "form_name": "Gynae 2WW",
        "recall": 0.91,
        "precision": 0.97,
    }
    breast = {
        "fingerprint": "sfh-breast-2ww",
        "form_name": "Breast 2WW",
        "recall": 0.4,
        "precision": 0.7,
    }
    report = {
        "referral_id": UBRN,
        "organization_id": "RK5",
        "service_name": "Gynae",
        "documents": [
            _row("recognised", "use_schema", gynae),
            _row("unrecognised", "pause", breast),
        ],
        "needs_review": True,
    }

    print_referral("neo4j+s://graph.example", report)

    out = capsys.readouterr().out
    assert "  Form: Gynae 2WW (sfh-gynae-2ww) recall 0.91 precision 0.97" in out
    assert "  Closest form: Breast 2WW (sfh-breast-2ww) recall 0.40" in out


def test_cli_referral_id_reads_the_graph_and_converts(
    capsys, monkeypatch, tmp_path: Path
) -> None:
    from scripts import recognise_form as cli

    context = ReferralContext(
        organization_id="RK5",
        organization_name="Example Trust",
        service_id="svc-1",
        service_name="Lower GI 2WW",
        documents=(
            ReferralDocument(
                doc_id="dr-19",
                title="Clinical information.docx",
                content_type=WORD,
                url="https://acct.blob.core.windows.net/letters/dr-19.docx",
            ),
            ReferralDocument(
                doc_id=f"{UBRN}-clinical-information",
                title="Clinical Information.pdf",
                content_type="",
                url="https://acct.blob.core.windows.net/letters/info.pdf",
            ),
        ),
    )
    pdf_reads: list[str] = []

    def read_pdf(content: bytes, filename: str) -> str:
        pdf_reads.append(filename)
        return document_by_id("devon-gynae-docx")

    monkeypatch.setattr(
        "scripts.recognise_referral.load_pdf_reader", lambda agents_repo: read_pdf
    )

    class _Open:
        def close(self) -> None:
            return None

    monkeypatch.setenv("NEO4J_URI", "neo4j+s://graph.example")
    monkeypatch.setenv("NEO4J_PASSWORD", "pw")
    monkeypatch.setattr(cli, "load_keyvault_secrets", lambda: None)
    monkeypatch.setattr("scripts.recognise_referral.load_storage_keys", lambda: 0)
    monkeypatch.setattr(cli, "open_read_only_graph", lambda: _Open())
    monkeypatch.setattr(
        "scripts.recognise_referral.load_referral_context",
        lambda graph, referral_id: context,
    )
    monkeypatch.setattr(
        "libs.pipeline.form_schema_candidates.load_candidate_schemas",
        lambda graph, organization_id: load_schema_dir(DEVON),
    )
    monkeypatch.setattr("scripts.recognise_referral.download_blob", lambda url: b"docx")
    monkeypatch.setattr(
        "scripts.recognise_referral.post_convert_html",
        lambda content, filename, content_type, converter_url: "<html>form</html>",
    )

    class _Parser:
        def convert_html_to_markdown(self, html_content: str) -> str:
            assert html_content == "<html>form</html>"
            return document_by_id("devon-gynae-docx")

    monkeypatch.setattr(
        "scripts.recognise_referral.load_markdown_parser",
        lambda agents_repo: _Parser(),
    )
    code = cli.main(
        [
            "--referral-id",
            UBRN,
            "--output-dir",
            str(tmp_path),
            "--converter-url",
            "http://localhost:8012",
            "--agents-repo",
            str(tmp_path),
        ]
    )
    assert code == 0
    assert "Decision: use this schema. Do not pause." in capsys.readouterr().out
    assert pdf_reads == ["Clinical Information.pdf"]


def test_cli_runs_without_pdfplumber_and_names_the_fix(
    monkeypatch, tmp_path: Path
) -> None:
    from scripts import recognise_form as cli

    def missing(agents_repo: Path) -> None:
        raise ModuleNotFoundError("No module named 'pdfplumber'")

    monkeypatch.setattr("scripts.recognise_referral.load_pdf_reader", missing)
    monkeypatch.setattr(
        "scripts.recognise_referral.load_markdown_parser", lambda agents_repo: None
    )
    args = cli._parse_args(["--referral-id", UBRN, "--agents-repo", str(tmp_path)])

    converters = cli._converters(args)

    assert converters["pdf_to_markdown"] is None


def test_convert_posts_html_to_the_doc_converter(monkeypatch) -> None:
    from scripts.recognise_referral import post_convert_html

    captured: dict[str, object] = {}

    class _Response:
        text = "<p>Hi</p>"

        def raise_for_status(self) -> None:
            return None

    class _Client:
        def __init__(self, timeout: float) -> None:
            captured["timeout"] = timeout

        def __enter__(self) -> "_Client":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, data: dict, files: dict) -> _Response:
            captured["url"] = url
            captured["data"] = data
            captured["files"] = files
            return _Response()

    monkeypatch.setattr("scripts.recognise_referral.httpx.Client", _Client)
    html = post_convert_html(
        b"abc",
        filename="a.docx",
        content_type=WORD,
        converter_url="http://localhost:8012/",
    )
    assert html == "<p>Hi</p>"
    assert captured["url"] == "http://localhost:8012/convert"
    assert captured["data"] == {"target_format": "html"}


def test_download_uses_the_storage_connection_string(monkeypatch) -> None:
    from scripts.recognise_referral import download_blob

    seen: dict[str, str] = {}

    class _Body:
        def readall(self) -> bytes:
            return b"file-bytes"

    class _Client:
        def __init__(self) -> None:
            return None

        @staticmethod
        def from_connection_string(
            conn: str, container_name: str, blob_name: str
        ) -> "_Client":
            seen["has_account"] = "AccountName=acct" in conn
            seen["container"] = container_name
            seen["name"] = blob_name
            return _Client()

        def download_blob(self) -> _Body:
            return _Body()

    monkeypatch.setenv(
        "PATIENT_DOCUMENT_STORAGE_CONNECTION_STRING",
        "AccountName=acct;AccountKey=not-a-real-key;",
    )
    monkeypatch.setattr("scripts.recognise_referral.BlobClient", _Client)
    data = download_blob("https://acct.blob.core.windows.net/letters/dr-19.docx")
    assert data == b"file-bytes"
    assert seen["has_account"] is True
    assert seen["container"] == "letters"
    assert seen["name"] == "dr-19.docx"


def test_storage_keys_load_from_local_secrets_when_key_vault_is_set(
    monkeypatch, tmp_path: Path
) -> None:
    from scripts.recognise_referral import (
        _connection_string_for_account,
        load_storage_keys,
    )

    secrets = tmp_path / ".env.secrets"
    secrets.write_text(
        "NEO4J_PASSWORD=not-for-this-loader\n"
        "PATIENT_DOCUMENT_STORAGE_CONNECTION_STRING="
        "AccountName=acct;AccountKey=not-a-real-key;\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AZURE_KEYVAULT_URL", "https://example.vault.azure.net")
    monkeypatch.delenv("PATIENT_DOCUMENT_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)

    load_storage_keys(secrets)

    assert _connection_string_for_account("acct")
    assert "NEO4J_PASSWORD" not in os.environ


def test_missing_storage_key_names_the_account(monkeypatch) -> None:
    from scripts.recognise_referral import BlobFetchError, download_blob

    def refuse(_url: str) -> bytes:
        raise BlobFetchError("ERROR: You do not have the required permissions")

    def http_fails(_url: str) -> bytes:
        raise RuntimeError("403")

    monkeypatch.delenv("PATIENT_DOCUMENT_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv(
        "PATIENT_DOCUMENT_EXTRA_STORAGE_CONNECTION_STRINGS", raising=False
    )
    monkeypatch.setattr("scripts.recognise_referral._http_get", http_fails)
    monkeypatch.setattr("scripts.recognise_referral._az_download", refuse)

    with pytest.raises(BlobFetchError) as caught:
        download_blob("https://acct.blob.core.windows.net/letters/dr-19.docx")

    message = str(caught.value)
    assert "No storage key for account acct" in message
    assert "PATIENT_DOCUMENT_STORAGE_CONNECTION_STRING" in message


def test_windows_az_command_is_the_cmd_file(monkeypatch) -> None:
    from scripts.recognise_referral import az_executable

    def which(name: str) -> str | None:
        if name == "az.cmd":
            return r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
        return None

    monkeypatch.setattr("scripts.recognise_referral.shutil.which", which)
    assert az_executable().endswith("az.cmd")


def test_az_download_uses_account_container_and_blob_name(tmp_path: Path) -> None:
    from scripts.recognise_referral import az_download_args

    args = az_download_args(
        "https://acct.blob.core.windows.net/letters/folder/dr-19.docx",
        tmp_path / "blob.bin",
    )
    assert args[0:4] == ["az", "storage", "blob", "download"]
    assert args[args.index("--account-name") + 1] == "acct"
    assert args[args.index("--container-name") + 1] == "letters"
    assert args[args.index("--name") + 1] == "folder/dr-19.docx"
    assert args[args.index("--auth-mode") + 1] == "login"
