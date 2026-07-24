"""Tests for stable recommendation_key resolution wired into NICE ingest.

Covers the two helpers extracted from ``_async_ingest`` in
``nice_guidance.py`` for this: ``_walk_chapter_recommendations`` (collects
recommendations without upserting them, so key matching can see every new
number first) and ``_resolve_and_upsert_recommendations`` (resolves
identity via ``recommendation_key_matcher`` then upserts).

Atlas trace:
  DI: DI-42246DA7
  DO: DO-F8C56339
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.routers.nice_guidance import (
    _resolve_and_upsert_recommendations,
    _walk_chapter_recommendations,
)


def _make_client(chapter_content: dict, section_uris: list[str], section_content: dict):
    client = MagicMock()
    client.get_chapter_content = AsyncMock(return_value=chapter_content)
    client.get_section_uris = MagicMock(return_value=section_uris)
    client.get_section_content = AsyncMock(return_value=section_content)
    return client


class TestWalkChapterRecommendations:
    async def test_collects_one_recommendation_per_section(self):
        chapters = [{"Title": "Referral", "Href": "/chapter-1.json"}]
        client = _make_client(
            chapter_content={"whatever": True},
            section_uris=["/section-1.1.json"],
            section_content={
                "Content": (
                    "<article class='numbered-paragraph' id='ng12-1_1_1'>"
                    "<h5>1.1.1</h5><p>Refer if rectal bleeding.</p></article>"
                )
            },
        )
        upserter = MagicMock()

        entries = await _walk_chapter_recommendations(
            client, upserter, "NG12", chapters, "NG12", "NG12:v1", "job-1"
        )

        assert len(entries) == 1
        assert entries[0]["chapter_id"] == "NG12:v1:CH000"
        assert entries[0]["item"]["Title"] == "1.1.1"
        upserter.upsert_chapter.assert_called_once()
        # Recommendation upserting must NOT happen here -- deferred to the
        # caller so key matching sees every new number first.
        upserter.upsert_recommendation.assert_not_called()

    async def test_chapter_with_no_href_is_skipped_without_error(self):
        chapters = [{"Title": "Appendix A"}]
        client = MagicMock()
        upserter = MagicMock()

        entries = await _walk_chapter_recommendations(
            client, upserter, "NG12", chapters, "NG12", "NG12:v1", "job-1"
        )

        assert entries == []
        upserter.upsert_chapter.assert_called_once()

    async def test_section_fetch_failure_is_skipped_without_error(self):
        chapters = [{"Title": "Referral", "Href": "/chapter-1.json"}]
        client = _make_client(
            chapter_content={},
            section_uris=["/section-1.1.json"],
            section_content={},
        )
        client.get_section_content = AsyncMock(side_effect=RuntimeError("boom"))
        upserter = MagicMock()

        entries = await _walk_chapter_recommendations(
            client, upserter, "NG12", chapters, "NG12", "NG12:v1", "job-1"
        )

        assert entries == []

    async def test_rec_ids_are_version_and_position_scoped(self):
        chapters = [{"Title": "Referral", "Href": "/chapter-1.json"}]
        client = _make_client(
            chapter_content={},
            section_uris=["/section-1.1.json"],
            section_content={
                "Content": (
                    "<article class='numbered-paragraph' id='ng12-1_1_1'>"
                    "<h5>1.1.1</h5><p>Refer if rectal bleeding.</p></article>"
                    "<article class='numbered-paragraph' id='ng12-1_1_2'>"
                    "<h5>1.1.2</h5><p>Offer a scan.</p></article>"
                )
            },
        )
        upserter = MagicMock()

        entries = await _walk_chapter_recommendations(
            client, upserter, "NG12", chapters, "NG12", "NG12:v2", "job-1"
        )

        assert [e["rec_id"] for e in entries] == [
            "NG12:v2:CH000:SEC000:R000",
            "NG12:v2:CH000:SEC000:R001",
        ]


class TestResolveAndUpsertRecommendations:
    def _entry(self, rec_id: str, chapter_id: str, number: str, text: str) -> dict:
        return {
            "rec_id": rec_id,
            "chapter_id": chapter_id,
            "item": {"Title": number, "Text": text},
        }

    def test_first_ingest_upserts_every_entry_with_a_fresh_key(self):
        entries = [
            self._entry("NG12:v1:CH000:SEC000:R000", "NG12:v1:CH000", "1.2.9", "text"),
        ]
        upserter = MagicMock()

        total = _resolve_and_upsert_recommendations(
            upserter, "NG12", "NG12:v1", entries, old_recs=[]
        )

        assert total == 1
        upserter.upsert_recommendation.assert_called_once()
        _, kwargs = upserter.upsert_recommendation.call_args
        assert kwargs["recommendation_key"]
        assert kwargs["renumbered_from"] is None

    def test_unchanged_number_carries_key_forward_no_renumbered_from(self):
        entries = [
            self._entry(
                "NG12:v2:CH000:SEC000:R000",
                "NG12:v2:CH000",
                "1.2.9",
                "Consider non-urgent endoscopy.",
            ),
        ]
        old_recs = [
            {
                "number": "1.2.9",
                "text": "Consider non-urgent endoscopy.",
                "recommendation_key": "stable-key-129",
            }
        ]
        upserter = MagicMock()

        _resolve_and_upsert_recommendations(
            upserter, "NG12", "NG12:v2", entries, old_recs
        )

        _, kwargs = upserter.upsert_recommendation.call_args
        assert kwargs["recommendation_key"] == "stable-key-129"
        assert kwargs["renumbered_from"] is None

    def test_renumbered_recommendation_carries_key_forward_with_renumbered_from(self):
        entries = [
            self._entry(
                "NG12:v2:CH000:SEC000:R000",
                "NG12:v2:CH000",
                "1.2.10",
                "Consider non-urgent endoscopy for unexplained haemoptysis.",
            ),
        ]
        old_recs = [
            {
                "number": "1.2.9",
                "text": "Consider non-urgent endoscopy for unexplained haemoptysis.",
                "recommendation_key": "stable-key-129",
            }
        ]
        upserter = MagicMock()

        _resolve_and_upsert_recommendations(
            upserter, "NG12", "NG12:v2", entries, old_recs
        )

        _, kwargs = upserter.upsert_recommendation.call_args
        assert kwargs["recommendation_key"] == "stable-key-129"
        assert kwargs["renumbered_from"] == "1.2.9"

    def test_old_recs_missing_number_are_ignored_not_crashed_on(self):
        entries = [
            self._entry("NG12:v2:CH000:SEC000:R000", "NG12:v2:CH000", "1.2.9", "text"),
        ]
        old_recs = [{"number": None, "text": "orphan", "recommendation_key": "k0"}]
        upserter = MagicMock()

        total = _resolve_and_upsert_recommendations(
            upserter, "NG12", "NG12:v2", entries, old_recs
        )

        assert total == 1

    def test_upserts_in_the_same_order_as_the_collected_entries(self):
        entries = [
            self._entry("r1", "ch", "1.1.1", "a"),
            self._entry("r2", "ch", "1.1.2", "b"),
        ]
        upserter = MagicMock()

        _resolve_and_upsert_recommendations(upserter, "NG12", "NG12:v1", entries, [])

        called_rec_ids = [
            c.args[1] for c in upserter.upsert_recommendation.call_args_list
        ]
        assert called_rec_ids == ["r1", "r2"]
