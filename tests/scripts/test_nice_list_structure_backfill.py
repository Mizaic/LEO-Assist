"""Unit tests for the NICE list-structure backfill migration script.

``scripts/migrations/2026_nice_list_structure_backfill.py`` backfills
``listStructureJson`` onto already-ingested NICE Recommendation nodes by
re-fetching and re-parsing the same NICE Syndication API section JSON a
fresh ingest would use -- see the highlight-to-build wizard plan's
"Ingestion" section (``nice-list-schema-backfill`` todo).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "services" / "api") not in sys.path:
    sys.path.insert(0, str(REPO / "services" / "api"))

# The migration filename starts with a digit (year prefix) so it cannot be
# imported via the normal package syntax. Load it from disk via importlib
# so the test exercises the same source the operator runs -- same pattern
# as test_link_or_delete_orphan_snomed_concepts.py.
_MIGRATION_PATH = (
    REPO / "scripts" / "migrations" / "2026_nice_list_structure_backfill.py"
)
_MIGRATION_MODULE_NAME = "nice_list_structure_backfill"
_spec = importlib.util.spec_from_file_location(_MIGRATION_MODULE_NAME, _MIGRATION_PATH)
assert _spec is not None and _spec.loader is not None
backfill = importlib.util.module_from_spec(_spec)
sys.modules[_MIGRATION_MODULE_NAME] = backfill
_spec.loader.exec_module(backfill)


def _make_session_mock(single_return: dict):
    session = MagicMock()
    result = MagicMock()
    result.single.return_value = single_return
    session.run.return_value = result
    return session


class TestFetchAllRecommendations:
    @pytest.mark.asyncio
    async def test_walks_every_chapter_and_section(self):
        client = MagicMock()
        client.get_chapters = AsyncMock(
            return_value=[{"Href": "https://api/chapter-1"}]
        )
        client.get_chapter_content = AsyncMock(return_value={"chapter": "data"})
        client.get_section_uris = MagicMock(return_value=["https://api/sec-1"])
        client.get_section_content = AsyncMock(
            return_value={
                "Content": (
                    "<article class='numbered-paragraph'><h5>1.1.1</h5>"
                    "<p>Refer if rectal bleeding.</p></article>"
                ),
                "SectionId": "sec-1",
            }
        )

        recs = await backfill.fetch_all_recommendations(client, "NG12")
        assert len(recs) == 1
        assert recs[0]["Title"] == "1.1.1"
        assert recs[0]["ListStructure"] is None

    @pytest.mark.asyncio
    async def test_skips_chapters_with_no_href(self):
        client = MagicMock()
        client.get_chapters = AsyncMock(return_value=[{}])
        client.get_chapter_content = AsyncMock()

        recs = await backfill.fetch_all_recommendations(client, "NG12")
        assert recs == []
        client.get_chapter_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_sections_that_fail_to_fetch(self):
        client = MagicMock()
        client.get_chapters = AsyncMock(return_value=[{"Href": "https://api/ch"}])
        client.get_chapter_content = AsyncMock(return_value={})
        client.get_section_uris = MagicMock(return_value=["https://api/sec-1"])
        client.get_section_content = AsyncMock(side_effect=RuntimeError("timeout"))

        recs = await backfill.fetch_all_recommendations(client, "NG12")
        assert recs == []

    @pytest.mark.asyncio
    async def test_carries_list_structure_through_for_structured_recs(self):
        client = MagicMock()
        client.get_chapters = AsyncMock(return_value=[{"Href": "https://api/ch"}])
        client.get_chapter_content = AsyncMock(return_value={})
        client.get_section_uris = MagicMock(return_value=["https://api/sec-1"])
        html = (
            "<article class='numbered-paragraph'><h5>1.2.9</h5>"
            "<div><p>Refer if:</p>"
            "<ul class='itemizedlist'>"
            "<li class='listitem'><p>haematemesis, or</p></li>"
            "<li class='listitem'><p>a raised platelet count</p></li>"
            "</ul></div></article>"
        )
        client.get_section_content = AsyncMock(
            return_value={"Content": html, "SectionId": "sec-1.2"}
        )

        recs = await backfill.fetch_all_recommendations(client, "NG12")
        assert recs[0]["ListStructure"] is not None
        assert len(recs[0]["ListStructure"]["items"]) == 2


class TestBackfillGuideline:
    def test_dry_run_reports_matches_without_writing(self):
        session = _make_session_mock({"matched": 1})
        recs = [
            {
                "Title": "1.2.9",
                "ListStructure": {"lead_text": "x", "items": [{"text": "a"}]},
            }
        ]
        updated, skipped = backfill.backfill_guideline(
            session, "NG12", recs, apply=False
        )
        assert (updated, skipped) == (1, 0)
        cypher = session.run.call_args[0][0]
        assert "SET" not in cypher

    def test_apply_writes_json_serialised_structure(self):
        session = _make_session_mock({"updated": 1})
        structure = {"lead_text": "x", "items": [{"text": "haematemesis"}]}
        recs = [{"Title": "1.2.9", "ListStructure": structure}]

        updated, skipped = backfill.backfill_guideline(
            session, "NG12", recs, apply=True
        )
        assert (updated, skipped) == (1, 0)
        kwargs = session.run.call_args[1]
        assert kwargs["guideline_id"] == "NG12"
        assert kwargs["number"] == "1.2.9"
        assert json.loads(kwargs["list_structure_json"]) == structure

    def test_skips_section_title_that_is_not_a_recommendation_number(self):
        """A shared section title must not paint one rec's list onto siblings."""
        session = _make_session_mock({"updated": 4})
        recs = [
            {
                "Title": "1.5 Gynaecological cancers",
                "ListStructure": {
                    "lead_text": "Consider an ultrasound if they have:",
                    "items": [
                        {"text": "unexplained vaginal discharge", "start": 0, "end": 10}
                    ],
                },
            }
        ]
        updated, skipped = backfill.backfill_guideline(
            session, "NG12", recs, apply=True
        )
        assert (updated, skipped) == (0, 1)
        session.run.assert_not_called()

    def test_skips_recs_with_no_list_structure(self):
        session = _make_session_mock({"matched": 1})
        recs = [{"Title": "1.1.1", "ListStructure": None}]
        updated, skipped = backfill.backfill_guideline(
            session, "NG12", recs, apply=False
        )
        assert (updated, skipped) == (0, 1)
        session.run.assert_not_called()

    def test_skips_when_no_matching_recommendation_node_exists(self):
        session = _make_session_mock({"matched": 0})
        recs = [
            {
                "Title": "1.2.9",
                "ListStructure": {"lead_text": "x", "items": [{"text": "a"}]},
            }
        ]
        updated, skipped = backfill.backfill_guideline(
            session, "NG12", recs, apply=False
        )
        assert (updated, skipped) == (0, 1)

    def test_lowercase_code_is_upper_cased_for_matching(self):
        session = _make_session_mock({"matched": 1})
        recs = [
            {
                "Title": "1.2.9",
                "ListStructure": {"lead_text": "x", "items": [{"text": "a"}]},
            }
        ]
        backfill.backfill_guideline(session, "ng12", recs, apply=False)
        kwargs = session.run.call_args[1]
        assert kwargs["guideline_id"] == "NG12"

    def test_running_twice_with_apply_is_idempotent(self):
        """Second pass writes the identical JSON -- a no-op SET, not a
        shape-transformation, so no special already-migrated check is
        needed (unlike the synonym-set migration this pattern mirrors)."""
        session = _make_session_mock({"updated": 1})
        structure = {"lead_text": "x", "items": [{"text": "haematemesis"}]}
        recs = [{"Title": "1.2.9", "ListStructure": structure}]

        backfill.backfill_guideline(session, "NG12", recs, apply=True)
        first_json = session.run.call_args[1]["list_structure_json"]
        backfill.backfill_guideline(session, "NG12", recs, apply=True)
        second_json = session.run.call_args[1]["list_structure_json"]
        assert first_json == second_json


class TestMainArgValidation:
    def test_requires_dry_run_or_apply(self):
        with pytest.raises(SystemExit):
            backfill.main(["--codes", "NG12"])
