"""The local form-recognition harness: markdown in, one result per document.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from libs.cypher.form_schema_queries import LIST_ACTIVE_FORM_SCHEMAS_FOR_ORG
from libs.form_recognition.schema_files import load_schema_file
from libs.pipeline.form_schema_store import _schema_to_sections_json
from scripts import recognise_form as cli
from tests.form_recognition_corpus import bundle_chunks, document_by_id, load_manifest

REPO = Path(__file__).resolve().parents[1]
CHUNKS = REPO / "tests" / "fixtures" / "form_schema" / "gynae_2ww_markdown_chunks.json"
DEVON = REPO / "tests" / "fixtures" / "form_recognition" / "schemas"


def _bundle(bundle_id: str) -> dict:
    return next(b for b in load_manifest()["bundles"] if b["id"].startswith(bundle_id))


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _json_run(capsys, *argv: str) -> dict:
    assert cli.main([*argv, "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def test_file_bundle_gives_one_result_per_document(tmp_path, capsys) -> None:
    text = "\n\n".join(bundle_chunks(_bundle("ubrn-shaped")))
    data = _json_run(capsys, "--file", str(_write(tmp_path, "b.md", text)))
    assert [d["outcome"] for d in data["documents"]] == [
        "unrecognised",
        "recognised",
    ]
    assert data["needs_review"] is True
    assert data["source"] == "templates"


def test_chunks_file_scores_stored_chunks(capsys) -> None:
    data = _json_run(capsys, "--chunks", str(CHUNKS))
    assert [d["outcome"] for d in data["documents"]] == ["recognised", "recognised"]
    assert {d["fingerprint"] for d in data["documents"]} == {
        "sfh-gynae-2ww-v1",
        "nhs-ers-clinical-information-v1",
    }
    assert data["needs_review"] is False


def test_chunks_file_may_be_a_plain_list_of_strings(tmp_path, capsys) -> None:
    chunks = bundle_chunks(_bundle("letter-plus-ers"))
    path = _write(tmp_path, "c.json", json.dumps(chunks))
    data = _json_run(capsys, "--chunks", str(path))
    assert [d["outcome"] for d in data["documents"]] == ["not_a_form", "recognised"]


def test_templates_option_scores_against_the_given_folder(tmp_path, capsys) -> None:
    path = _write(tmp_path, "f.md", document_by_id("devon-gynae-docx"))
    data = _json_run(capsys, "--file", str(path), "--templates", str(DEVON))
    (doc,) = data["documents"]
    assert doc["outcome"] == "recognised"
    assert doc["fingerprint"] == "devon-uscp-gynae-v8"


def test_text_output_names_the_closest_form_and_missing_headings(
    tmp_path, capsys
) -> None:
    path = _write(tmp_path, "f.md", document_by_id("sfh-gynae-new-version"))
    assert cli.main(["--file", str(path)]) == 0
    out = capsys.readouterr().out
    assert "Not recognised" in out
    assert "Closest form:" in out
    assert "Missing:" in out
    assert "A person needs to review this referral." in out


def test_file_and_chunks_together_is_a_usage_error(tmp_path) -> None:
    path = _write(tmp_path, "f.md", "text")
    with pytest.raises(SystemExit):
        cli.main(["--file", str(path), "--chunks", str(path)])


class _FakeGraph:
    def __init__(self, rows=None, error: Exception | None = None) -> None:
        self.rows = rows or []
        self.error = error
        self.queries: list[tuple[str, dict]] = []

    def run(self, query: str, **params):
        cli.assert_read_only(query)
        self.queries.append((query, params))
        if self.error is not None:
            raise self.error
        return self.rows

    def close(self) -> None:
        return None


def _gynae_row() -> dict:
    path = REPO / "tests" / "fixtures" / "form_schema" / "sfh_gynae_2ww_template.json"
    schema = load_schema_file(path, fingerprint="sfh-gynae-2ww-v1")
    return {
        "schema_id": "s1",
        "fingerprint": "sfh-gynae-2ww-v1",
        "form_name": schema.form_name,
        "sections_json": _schema_to_sections_json(schema),
    }


def test_from_graph_prints_neo4j_uri_first_and_only_reads(
    tmp_path, capsys, monkeypatch
) -> None:
    graph = _FakeGraph(rows=[_gynae_row()])
    monkeypatch.setattr(cli, "load_keyvault_secrets", lambda: None)
    monkeypatch.setattr(cli, "open_read_only_graph", lambda: graph)
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://example.invalid")
    path = _write(tmp_path, "f.md", document_by_id("sfh-gynae-synthetic"))
    rc = cli.main(["--file", str(path), "--from-graph", "--organization-id", "RK5"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.splitlines()[0] == "NEO4J_URI: neo4j+s://example.invalid"
    assert graph.queries and graph.queries[0][1] == {"organization_id": "RK5"}
    assert "Recognised" in out


def test_from_graph_error_fails_loudly(tmp_path, capsys, monkeypatch) -> None:
    graph = _FakeGraph(error=RuntimeError("connection refused"))
    monkeypatch.setattr(cli, "load_keyvault_secrets", lambda: None)
    monkeypatch.setattr(cli, "open_read_only_graph", lambda: graph)
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://example.invalid")
    path = _write(tmp_path, "f.md", "anything")
    assert cli.main(["--file", str(path), "--from-graph"]) == 1
    assert "could not check" in capsys.readouterr().err


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s) SET s.x = 1",
        "MERGE (s:FormSchema {fingerprint: 'x'})",
        "CREATE (n)",
        "MATCH (n) DETACH DELETE n",
        "CALL apoc.create.node([], {})",
    ],
)
def test_read_only_guard_refuses_write_cypher(query: str) -> None:
    with pytest.raises(ValueError):
        cli.assert_read_only(query)


def test_read_only_guard_allows_the_candidate_query() -> None:
    cli.assert_read_only(LIST_ACTIVE_FORM_SCHEMAS_FOR_ORG)
