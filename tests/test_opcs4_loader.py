"""VT-LEO-AI-218: NHS OPCS-4 reference-data loader.

Covers DI-LEO-AI-226, DO-LEO-AI-223, R-LEO-AI-209.

Verifies:
  - Code normalisation (A011 -> A01.1, A01 unchanged, single letter unchanged)
  - Level classification (chapter | category | code)
  - Streaming parser handles tab and multi-space delimiters and skips blanks
  - Synthesised chapter/category nodes when source omits them
  - Hierarchy edges close at the chapter root
  - MERGE-on-code is idempotent across reruns
  - Title backfill on bare nodes left by load_opcs4_map
  - Drift detection (titles_first_time vs titles_drifted)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.terminology.scripts.loaders import opcs4 as mod

# -- Pure-unit tests for parsing helpers ----------------------------------


class TestNormalise:
    def test_chapter_unchanged(self):
        assert mod._normalise_code("A") == "A"

    def test_category_unchanged(self):
        assert mod._normalise_code("A01") == "A01"

    def test_undotted_code_gets_dot(self):
        assert mod._normalise_code("A011") == "A01.1"

    def test_dotted_code_unchanged(self):
        assert mod._normalise_code("A01.1") == "A01.1"

    def test_lowercase_normalised(self):
        assert mod._normalise_code("a011") == "A01.1"

    def test_blank_unchanged(self):
        assert mod._normalise_code("") == ""


class TestClassifyLevel:
    def test_chapter(self):
        assert mod._classify_level("A") == "chapter"

    def test_category(self):
        assert mod._classify_level("A01") == "category"

    def test_code(self):
        assert mod._classify_level("A01.1") == "code"


class TestStreamRows:
    def test_skips_blank_and_comment_lines(self, tmp_path: Path):
        p = tmp_path / "opcs.txt"
        p.write_text(
            "# header comment\n"
            "\n"
            "A01.1\tHemispherectomy\n"
            "A02.1\tStereotactic ablation of brain\n",
            encoding="utf-8",
        )
        rows = list(mod._stream_rows(p))
        assert rows == [
            ("A01.1", "Hemispherectomy"),
            ("A02.1", "Stereotactic ablation of brain"),
        ]

    def test_handles_multispace_delimiter(self, tmp_path: Path):
        p = tmp_path / "opcs.txt"
        p.write_text("A01.1     Hemispherectomy\n", encoding="utf-8")
        rows = list(mod._stream_rows(p))
        assert rows == [("A01.1", "Hemispherectomy")]


class TestBuildNodeRows:
    def test_synthesises_chapter_and_category_when_source_omits_them(self):
        rows = [("A011", "Hemispherectomy")]
        nodes, parents = mod._build_node_rows(rows, edition="OPCS-4 Apr 2024")

        codes = {n["code"]: n for n in nodes}
        assert {"A01.1", "A01", "A"} == set(codes.keys())
        assert codes["A01.1"]["title"] == "Hemispherectomy"
        assert codes["A"]["title"] == mod._CHAPTER_NAMES["A"]
        assert codes["A01"]["title"] == ""
        assert codes["A01.1"]["level"] == "code"
        assert codes["A01"]["level"] == "category"
        assert codes["A"]["level"] == "chapter"

        edges = {(p["child"], p["parent"]) for p in parents}
        assert ("A01.1", "A01") in edges
        assert ("A01", "A") in edges

    def test_keeps_provided_category_title(self):
        rows = [
            ("A01", "Major excision of brain"),
            ("A011", "Hemispherectomy"),
        ]
        nodes, _parents = mod._build_node_rows(rows, edition="x")
        codes = {n["code"]: n for n in nodes}
        assert codes["A01"]["title"] == "Major excision of brain"

    def test_dedupes_parent_edges(self):
        rows = [
            ("A011", "Hemispherectomy"),
            ("A012", "Total hemispherectomy"),
        ]
        _nodes, parents = mod._build_node_rows(rows, edition="x")
        cat_to_chap = [p for p in parents if p["child"] == "A01" and p["parent"] == "A"]
        assert len(cat_to_chap) == 1


# -- End-to-end loader against a mocked AsyncDriver -----------------------


@pytest.fixture
def fixture_file(tmp_path: Path) -> Path:
    p = tmp_path / "OPCS49 CodesAndTitles Nov 2024.txt"
    p.write_text(
        "A01.1\tHemispherectomy\n"
        "A01.2\tTotal lobectomy of brain\n"
        "B01.1\tTotal excision of pituitary gland\n",
        encoding="utf-8",
    )
    return p


class _FakeAsyncSession:
    def __init__(self, store: dict):
        self._store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute_write(self, fn):
        class _Tx:
            def __init__(self, store):
                self._store = store

            async def run(self, cypher, rows=None, **extra):
                self._store.setdefault("writes", []).append(
                    {"cypher": cypher, "rows": rows, "extra": extra}
                )

        await fn(_Tx(self._store))

    async def run(self, query: str, **params):
        prior = self._store.get("prior_titles", {})
        codes = params.get("codes", [])
        items = [{"code": c, "title": prior[c]} for c in codes if c in prior]

        class _Result:
            def __aiter__(self_inner):
                async def _iter():
                    for item in items:
                        yield item

                return _iter()

        return _Result()


class _FakeDriver:
    def __init__(self, store: dict):
        self._store = store

    def session(self):
        return _FakeAsyncSession(self._store)


@pytest.mark.asyncio
async def test_full_load_writes_nodes_and_parents(fixture_file):
    store: dict = {}
    driver = _FakeDriver(store)
    summary = await mod.load_opcs4(driver, fixture_file, batch_size=1000)

    # 3 codes + 2 categories (A01, B01) + 2 chapters (A, B)
    assert summary["nodes_upserted"] == 7
    # 3 code->category + 2 category->chapter
    assert summary["is_a_edges_upserted"] == 5
    # All real titles are first-time (empty category title doesn't count)
    assert summary["titles_first_time"] == 5  # 3 codes + 2 chapters with names
    assert summary["titles_drifted"] == 0


@pytest.mark.asyncio
async def test_load_is_idempotent_on_rerun(fixture_file):
    store: dict = {
        "prior_titles": {
            "A01.1": "Hemispherectomy",
            "A01.2": "Total lobectomy of brain",
            "B01.1": "Total excision of pituitary gland",
            "A": mod._CHAPTER_NAMES["A"],
            "B": mod._CHAPTER_NAMES["B"],
        },
    }
    driver = _FakeDriver(store)
    summary = await mod.load_opcs4(driver, fixture_file, batch_size=1000)
    assert summary["titles_first_time"] == 0
    assert summary["titles_drifted"] == 0


@pytest.mark.asyncio
async def test_load_backfills_titles_on_bare_nodes(fixture_file):
    # Bare nodes left by load_opcs4_map carry empty titles.
    store: dict = {"prior_titles": {"A01.1": "", "A01.2": "", "B01.1": ""}}
    driver = _FakeDriver(store)
    summary = await mod.load_opcs4(driver, fixture_file, batch_size=1000)
    assert summary["titles_first_time"] >= 3


@pytest.mark.asyncio
async def test_load_detects_title_drift(fixture_file):
    store: dict = {"prior_titles": {"A01.1": "Old hemispherectomy title"}}
    driver = _FakeDriver(store)
    summary = await mod.load_opcs4(driver, fixture_file, batch_size=1000)
    assert summary["titles_drifted"] == 1


@pytest.mark.asyncio
async def test_load_writes_use_merge_node_cypher(fixture_file):
    store: dict = {}
    driver = _FakeDriver(store)
    await mod.load_opcs4(driver, fixture_file, batch_size=1000)
    cyphers = [w["cypher"] for w in store["writes"]]
    assert any("MERGE (c:OpcsCode {code: r.code})" in q for q in cyphers)
    assert any("MERGE (child)-[:IS_A]->(parent)" in q for q in cyphers)
