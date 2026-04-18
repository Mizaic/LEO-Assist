"""VT-LEO-AI-301: NHS ICD-10 5th Edition XML loader.

Covers DI-LEO-AI-228, DO-LEO-AI-301, R-LEO-AI-301.

Verifies:
  - Code normalisation (I500 -> I50.0; I50 unchanged; chapter unchanged)
  - Level classification (chapter | block | category | code)
  - Title extraction (preferred Rubric wins over fallback)
  - IS_A hierarchy is materialised end-to-end (code -> chapter)
  - MERGE-on-code is idempotent across reruns
  - Bare nodes left by SNOMED ExtendedMap gain titles in-place
  - Drift detection (titles_first_time vs titles_drifted)
"""

from __future__ import annotations

from pathlib import Path
import pytest

from services.terminology.scripts.loaders import icd10_xml as mod

# -- Pure-unit tests for parsing helpers ----------------------------------


class TestNormalise:
    def test_dot_form_unchanged(self):
        assert mod._normalise_code("I50.0") == "I50.0"

    def test_undotted_4char_gets_dot(self):
        assert mod._normalise_code("I500") == "I50.0"

    def test_three_char_unchanged(self):
        assert mod._normalise_code("I50") == "I50"

    def test_chapter_unchanged(self):
        assert mod._normalise_code("IX") == "IX"

    def test_block_with_dash_unchanged(self):
        assert mod._normalise_code("I30-I52") == "I30-I52"

    def test_blank(self):
        assert mod._normalise_code("") == ""


class TestClassifyLevel:
    def test_chapter_kind_wins(self):
        assert mod._classify_level("chapter", "IX") == "chapter"

    def test_block_kind_wins(self):
        assert mod._classify_level("block", "I30-I52") == "block"

    def test_dotted_code_is_code(self):
        assert mod._classify_level("category", "I50.0") == "code"

    def test_three_char_is_category(self):
        assert mod._classify_level("category", "I50") == "category"

    def test_dash_is_block_when_kind_unknown(self):
        assert mod._classify_level("", "I30-I52") == "block"


# -- Streaming parse against a fixture XML --------------------------------


CLAML_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<ClaML version="2.0.0">
  <Title name="ICD-10" date="2024-04-01" />
  <Class code="IX" kind="chapter">
    <Rubric kind="preferred"><Label>Diseases of the circulatory system</Label></Rubric>
  </Class>
  <Class code="I30-I52" kind="block">
    <SuperClass code="IX" />
    <Rubric kind="preferred"><Label>Other forms of heart disease</Label></Rubric>
  </Class>
  <Class code="I50" kind="category">
    <SuperClass code="I30-I52" />
    <Rubric kind="preferred"><Label>Heart failure</Label></Rubric>
  </Class>
  <Class code="I500" kind="category">
    <SuperClass code="I50" />
    <Rubric kind="preferred"><Label>Congestive heart failure</Label></Rubric>
    <Meta name="age" value="adult" />
    <Meta name="sex" value="any" />
  </Class>
</ClaML>
"""


@pytest.fixture
def fixture_xml(tmp_path: Path) -> Path:
    p = tmp_path / "icd10.xml"
    p.write_text(CLAML_FIXTURE, encoding="utf-8")
    return p


class TestIterClasses:
    def test_yields_every_class_once(self, fixture_xml):
        rows = list(mod._iter_classes(fixture_xml))
        codes = [r[0] for r in rows]
        assert codes == ["IX", "I30-I52", "I50", "I500"]

    def test_extracts_preferred_title(self, fixture_xml):
        rows = list(mod._iter_classes(fixture_xml))
        titles = {r[0]: r[3] for r in rows}
        assert titles["I500"] == "Congestive heart failure"

    def test_extracts_meta_constraints(self, fixture_xml):
        rows = list(mod._iter_classes(fixture_xml))
        i500 = next(r for r in rows if r[0] == "I500")
        _raw_code, _kind, _parent, _title, age, sex = i500
        assert age == "adult"
        assert sex == "any"


# -- End-to-end loader against a mocked AsyncDriver -----------------------


class _FakeAsyncSession:
    """Captures BatchWriter writes for verification."""

    def __init__(self, store: dict):
        self._store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute_write(self, fn):
        # The loader's _tx callback runs `tx.run(cypher, rows=..., **extra)`.
        captured: dict = {}

        class _Tx:
            async def run(self_inner, cypher, rows=None, **extra):
                captured["cypher"] = cypher
                captured["rows"] = rows
                captured["extra"] = extra

        await fn(_Tx())
        self._store.setdefault("writes", []).append(captured)

    async def run(self, query: str, **params):
        # Used by _existing_titles - return prior_titles configured in store.
        prior = self._store.get("prior_titles", {})
        codes = params.get("codes", [])

        class _Result:
            def __init__(self, items):
                self._items = items

            def __aiter__(self):
                async def _iter():
                    for item in self._items:
                        yield item

                return _iter()

        items = [
            {"code": code, "title": prior[code]} for code in codes if code in prior
        ]
        return _Result(items)


class _FakeDriver:
    def __init__(self, store: dict):
        self._store = store

    def session(self):
        return _FakeAsyncSession(self._store)


@pytest.mark.asyncio
async def test_full_load_writes_nodes_and_parents(fixture_xml):
    store: dict = {}
    driver = _FakeDriver(store)
    summary = await mod.load_icd10_xml(driver, fixture_xml, batch_size=1000)

    assert summary["nodes_upserted"] == 4
    assert summary["is_a_edges_upserted"] == 3
    # I500 / I50 / I30-I52 each have a title, IX too -> all four are first-time
    assert summary["titles_first_time"] == 4
    assert summary["titles_drifted"] == 0


@pytest.mark.asyncio
async def test_load_is_idempotent_on_rerun(fixture_xml):
    store: dict = {
        "prior_titles": {
            "IX": "Diseases of the circulatory system",
            "I30-I52": "Other forms of heart disease",
            "I50": "Heart failure",
            "I50.0": "Congestive heart failure",
        },
    }
    driver = _FakeDriver(store)
    summary = await mod.load_icd10_xml(driver, fixture_xml, batch_size=1000)
    assert summary["titles_first_time"] == 0
    assert summary["titles_drifted"] == 0


@pytest.mark.asyncio
async def test_load_backfills_titles_on_bare_nodes(fixture_xml):
    # Pre-existing bare nodes (from SNOMED ExtendedMap) carry an empty title.
    store: dict = {
        "prior_titles": {"I50.0": ""},
    }
    driver = _FakeDriver(store)
    summary = await mod.load_icd10_xml(driver, fixture_xml, batch_size=1000)
    assert summary["titles_first_time"] >= 1


@pytest.mark.asyncio
async def test_load_detects_title_drift(fixture_xml):
    store: dict = {
        "prior_titles": {"I50.0": "Old title from prior edition"},
    }
    driver = _FakeDriver(store)
    summary = await mod.load_icd10_xml(driver, fixture_xml, batch_size=1000)
    assert summary["titles_drifted"] >= 1


@pytest.mark.asyncio
async def test_load_writes_use_merge_node_cypher(fixture_xml):
    store: dict = {}
    driver = _FakeDriver(store)
    await mod.load_icd10_xml(driver, fixture_xml, batch_size=1000)
    cyphers = [w["cypher"] for w in store["writes"]]
    assert any("MERGE (c:Icd10Code {code: r.code})" in q for q in cyphers)
    assert any("MERGE (child)-[:IS_A]->(parent)" in q for q in cyphers)
