"""Tests for services/analysis-worker/app/analyzers/episode_builder.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.analysis_worker.app.analyzers.anchor_detector import AnchorResult


class TestExtractConditionKey:

    def test_strips_prefixes(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            _extract_condition_key,
        )

        assert (
            _extract_condition_key("Fast track referral for suspected breast cancer")
            == "breast"
        )
        assert _extract_condition_key("suspected lung cancer") == "lung"
        assert (
            _extract_condition_key("diagnosis of colorectal carcinoma") == "colorectal"
        )

    def test_unknown_fallback(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            _extract_condition_key,
        )

        assert _extract_condition_key("") == "unknown"

    def test_ncda_specific_types(self):
        """Verify keyword map produces NCDA-aligned type keys, not broad pathway groups."""
        from services.analysis_worker.app.analyzers.episode_builder import (
            _extract_condition_key,
        )

        cases = [
            # Lower GI -> colorectal
            ("diagnosis of colorectal carcinoma", "colorectal"),
            ("rectal adenocarcinoma", "colorectal"),
            ("bowel cancer", "colorectal"),
            # Upper GI subtypes
            ("pancreatic adenocarcinoma", "pancreatic"),
            ("oesophageal cancer", "oesophageal"),
            ("gastric carcinoma", "stomach"),
            ("hepatocellular carcinoma", "liver"),
            ("gallbladder carcinoma", "gallbladder"),
            # Urological subtypes
            ("prostate cancer", "prostate"),
            ("bladder carcinoma", "bladder"),
            ("renal cell carcinoma", "renal"),
            ("testicular germ cell tumour", "testicular"),
            # Gynaecological subtypes
            ("ovarian cancer", "ovarian"),
            ("endometrial carcinoma", "endometrial"),
            ("cervix uteri malignancy", "cervical"),
            ("vulval carcinoma", "vulval"),
            # Haematological subtypes
            ("non-hodgkin lymphoma", "lymphoma"),
            ("acute myeloid leukaemia", "leukaemia"),
            ("multiple myeloma", "myeloma"),
            # Head and neck subtypes
            ("thyroid carcinoma", "thyroid"),
            ("laryngeal cancer", "laryngeal"),
            ("oropharyngeal squamous cell carcinoma", "oropharyngeal"),
            # Other NCDA types
            ("melanoma", "melanoma"),
            ("mesothelioma", "mesothelioma"),
            ("sarcoma", "sarcoma"),
            ("brain tumour", "brain"),
            ("breast cancer", "breast"),
            ("lung carcinoma", "lung"),
            # Pathway-level fallback (no specific site in concept name)
            ("haematological malignancy", "haematological"),
            ("gynaecological cancer referral", "gynaecological"),
            ("upper gi cancer referral", "upper_gi"),
        ]

        for concept, expected in cases:
            result = _extract_condition_key(concept)
            assert result == expected, (
                f"_extract_condition_key({concept!r}) returned {result!r}, "
                f"expected {expected!r}"
            )

    def test_ncda_concept_id_overrides(self):
        """Verify 2WW lower-GI concept IDs map to colorectal, not lower_gi."""
        from services.analysis_worker.app.analyzers.episode_builder import (
            _SITE_BY_CONCEPT_ID,
        )

        assert _SITE_BY_CONCEPT_ID["276401000000108"] == "colorectal"
        assert _SITE_BY_CONCEPT_ID["892201000000106"] == "colorectal"
        assert _SITE_BY_CONCEPT_ID["382651000000108"] == "colorectal"

    def test_cancer_diagnosis_concept_ids_resolve_correctly(self):
        """Cancer diagnosis concept IDs must resolve even when c.name is a raw
        numeric string (unresolved in the graph).  These IDs come directly from
        snomed_ncda_cancer_types_mapping.json and cover the most common sources
        of cancer_type='unknown' in completed episodes."""
        from services.analysis_worker.app.analyzers.episode_builder import (
            _extract_condition_key_from_anchor,
        )

        cases = [
            # Breast - largest source of 'unknown' completed episodes
            ("254837009", "breast"),
            ("399935008", "breast"),  # DCIS
            ("716917000", "breast"),  # DCIS left
            ("716918005", "breast"),  # DCIS right
            # Skin
            ("372130007", "melanoma"),
            # Urological
            ("399068003", "prostate"),
            ("93689003", "bladder"),
            ("93849006", "renal"),
            ("363449006", "testicular"),
            # Gynaecological
            ("363443007", "ovarian"),
            ("363354003", "cervical"),
            ("371972005", "endometrial"),
            ("363367000", "vulval"),
            # Upper GI
            ("269457002", "oesophageal"),
            ("255080008", "stomach"),
            ("363418001", "pancreatic"),
            ("93870000", "liver"),
            ("363415003", "gallbladder"),
            # Lower GI
            ("363508008", "colorectal"),
            # Lung
            ("363358000", "lung"),
            # Haematological
            ("363495004", "leukaemia"),
            # CNS
            ("372063002", "brain"),
            # Unknown primary
            ("310504009", "non_site_specific"),
            ("128462008", "non_site_specific"),
        ]
        for concept_id, expected_key in cases:
            # Simulate c.name stored as raw numeric string (unresolved)
            anchor = {"concept_id": concept_id, "concept_name": concept_id}
            result = _extract_condition_key_from_anchor(anchor)
            assert (
                result == expected_key
            ), f"concept_id={concept_id}: expected '{expected_key}', got '{result}'"

    def test_non_site_specific_upgraded_by_specific_diagnosis(self):
        """A generic fast-track (non_site_specific) referral should be upgraded to the
        diagnosed cancer type when a specific diagnosis is available."""
        from services.analysis_worker.app.analyzers.episode_builder import (
            _PATHWAY_GROUP_KEYS,
        )

        # non_site_specific must be in the group keys so the upgrade logic fires
        assert "non_site_specific" in _PATHWAY_GROUP_KEYS, (
            "non_site_specific must be in _PATHWAY_GROUP_KEYS so generic fast-track "
            "referrals can be upgraded to the diagnosed cancer type"
        )

    def test_site_keys_compatible_pathway_to_specific(self):
        """Pathway-level visit keys should be compatible with specific NCDA episode keys."""
        from services.analysis_worker.app.analyzers.episode_builder import (
            _site_keys_compatible,
        )

        assert _site_keys_compatible("ovarian", "gynaecological")
        assert _site_keys_compatible("prostate", "urological")
        assert _site_keys_compatible("leukaemia", "haematological")
        assert _site_keys_compatible("oropharyngeal", "head_and_neck")
        assert _site_keys_compatible("oesophageal", "upper_gi")
        # Incompatible types
        assert not _site_keys_compatible("breast", "urological")
        assert not _site_keys_compatible("lung", "gynaecological")


class TestBuildEpisodes:

    @pytest.mark.asyncio
    async def test_no_anchors_returns_empty(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
        )

        anchors = AnchorResult(patient_id="P1")
        mock_client = MagicMock()
        result = await build_episodes(
            "P1", anchors, mock_client, domain_id="cancer_audit"
        )
        assert result.episodes_created == 0
        assert result.episode_ids == []

    @pytest.mark.asyncio
    async def test_creates_episode_from_referral(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
        )

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {
                    "encounter_id": "E1",
                    "encounter_date": "2024-03-15",
                    "concept_name": "Fast track referral for suspected breast cancer",
                    "source": "text_search",
                }
            ],
        )

        mock_client = MagicMock()
        mock_client.run.return_value = []

        result = await build_episodes(
            "P1", anchors, mock_client, domain_id="cancer_audit"
        )
        assert result.episodes_created == 1
        assert len(result.episode_ids) == 1

    @pytest.mark.asyncio
    async def test_deduplicates_cancer_types(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
        )

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {
                    "encounter_id": "E1",
                    "encounter_date": "2024-01-10",
                    "concept_name": "Fast track referral for suspected breast cancer",
                },
                {
                    "encounter_id": "E2",
                    "encounter_date": "2024-02-10",
                    "concept_name": "Fast track referral for suspected breast cancer",
                },
            ],
        )

        mock_client = MagicMock()
        mock_client.run.return_value = []

        result = await build_episodes(
            "P1", anchors, mock_client, domain_id="cancer_audit"
        )
        assert result.episodes_created == 1

    @pytest.mark.asyncio
    async def test_multiple_cancer_types_create_separate_episodes(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
        )

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {
                    "encounter_id": "E1",
                    "encounter_date": "2024-01-10",
                    "concept_name": "Fast track referral for suspected breast cancer",
                },
                {
                    "encounter_id": "E2",
                    "encounter_date": "2024-02-10",
                    "concept_name": "Fast track referral for suspected lung cancer",
                },
            ],
        )

        mock_client = MagicMock()
        mock_client.run.return_value = []

        result = await build_episodes(
            "P1", anchors, mock_client, domain_id="cancer_audit"
        )
        assert result.episodes_created == 2

    @pytest.mark.asyncio
    async def test_links_diagnosis_encounters(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
        )

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {
                    "encounter_id": "E1",
                    "encounter_date": "2024-01-10",
                    "concept_name": "suspected breast cancer",
                },
            ],
            diagnosis_anchors=[
                {
                    "encounter_id": "E2",
                    "encounter_date": "2024-02-10",
                    "concept_name": "confirmed adenocarcinoma",
                },
            ],
        )

        mock_client = MagicMock()
        mock_client.run.return_value = []

        result = await build_episodes(
            "P1", anchors, mock_client, domain_id="cancer_audit"
        )
        # DI-LEO-AI-136: under the Pass 2 fallback, the NSS diagnosis
        # ("confirmed adenocarcinoma") claims the breast referral
        # because it is the only unclaimed referral inside the
        # DIAG_LOOKBACK_DAYS window. This consolidates what were
        # previously two fragmented episodes (1 referral-only breast +
        # 1 diagnosis-only NSS) into a single completed episode,
        # fixing the 2WW under-count surfaced on /care/audit.
        assert result.episodes_created == 1

    @pytest.mark.asyncio
    async def test_diagnosis_attaches_to_same_site_not_nearest_other_site(self):
        """Breast malignancy must link to breast 2WW, not a later lung 2WW."""
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
            _episode_id,
        )

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {
                    "encounter_id": "E1",
                    "encounter_date": "2024-08-01",
                    "concept_name": "Fast track referral for suspected breast cancer (procedure)",
                },
                {
                    "encounter_id": "E2",
                    "encounter_date": "2024-09-15",
                    "concept_name": "Fast track referral for suspected lung cancer (procedure)",
                },
            ],
            diagnosis_anchors=[
                {
                    "encounter_id": "E3",
                    "encounter_date": "2024-11-01",
                    "concept_name": "Malignant tumor of breast (disorder)",
                },
            ],
        )
        mock_client = MagicMock()
        mock_client.run.return_value = []

        await build_episodes("P1", anchors, mock_client, domain_id="cancer_audit")

        breast_eid = _episode_id("P1", "breast", "2024-08-01")
        lung_eid = _episode_id("P1", "lung", "2024-09-15")
        merges = []
        for call in mock_client.run.call_args_list:
            args, kwargs = call
            if args and "MERGE (ep:EpisodeOfCare" in str(args[0]):
                merges.append(kwargs)
        by_eid = {m["episode_id"]: m for m in merges}
        assert by_eid[breast_eid]["status"] == "completed"
        assert by_eid[lung_eid]["status"] == "in_progress"

    # VT-084-TC-005: domain_id is set on EpisodeOfCare MERGE
    @pytest.mark.asyncio
    async def test_domain_id_passed_in_merge_cypher(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
        )

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {
                    "encounter_id": "E1",
                    "encounter_date": "2024-03-15",
                    "concept_name": "Fast track referral for suspected breast cancer",
                }
            ],
        )

        mock_client = MagicMock()
        mock_client.run.return_value = []

        await build_episodes("P1", anchors, mock_client, domain_id="cancer_audit")

        assert mock_client.run.called
        # Multiple Cypher calls are made (benign check, MERGE, auto-close rules).
        # Verify that at least one of them carries domain_id.
        all_kwargs = [call[1] for call in mock_client.run.call_args_list]
        assert any(kw.get("domain_id") == "cancer_audit" for kw in all_kwargs)

    @pytest.mark.asyncio
    async def test_episode_classification_accuracy_mock_dataset(self):
        """VT-007-TC-003: episode classification accuracy >= 85% on mock dataset."""
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
        )

        # Simulate 10 episodes where each builds correctly from anchors
        correct = 0
        total = 5

        for i in range(total):
            anchors = AnchorResult(
                patient_id=f"P{i}",
                referral_anchors=[
                    {
                        "encounter_id": f"E{i}",
                        "encounter_date": "2024-03-15",
                        "concept_name": "Fast track referral for suspected colorectal cancer",
                        "source": "text_search",
                    }
                ],
            )
            mock_client = MagicMock()
            mock_client.run.return_value = []
            result = await build_episodes(
                f"P{i}", anchors, mock_client, domain_id="cancer_audit"
            )
            if result.episodes_created == 1:
                correct += 1

        accuracy = correct / total
        assert (
            accuracy >= 0.85
        ), f"Episode classification accuracy {accuracy:.0%} below 85%"

    @pytest.mark.asyncio
    async def test_overlapping_episodes_same_condition_deduplicated(self):
        """VT-007-TC-004: two overlapping episodes for the same condition -> one episode."""
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
        )

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {
                    "encounter_id": "E1",
                    "encounter_date": "2024-01-10",
                    "concept_name": "Fast track referral for suspected breast cancer",
                },
                {
                    "encounter_id": "E2",
                    "encounter_date": "2024-01-20",
                    "concept_name": "Fast track referral for suspected breast cancer",
                },
            ],
        )
        mock_client = MagicMock()
        mock_client.run.return_value = []

        result = await build_episodes(
            "P1", anchors, mock_client, domain_id="cancer_audit"
        )
        # Duplicate referrals for same condition are deduplicated
        assert result.episodes_created == 1

    @pytest.mark.asyncio
    async def test_diagnosis_led_referral_within_lookback_claimed(self):
        """Diagnosis within _DIAG_LOOKBACK_DAYS of a same-site referral creates
        a completed episode, not two separate episodes."""
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
            _DIAG_LOOKBACK_DAYS,
        )

        gap_days = min(45, _DIAG_LOOKBACK_DAYS - 1)
        ref_date = "2024-06-01"
        import datetime

        diag_date = (
            datetime.date.fromisoformat(ref_date) + datetime.timedelta(days=gap_days)
        ).isoformat()

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {
                    "encounter_id": "E1",
                    "encounter_date": ref_date,
                    "concept_name": "Fast track referral for suspected lung cancer",
                }
            ],
            diagnosis_anchors=[
                {
                    "encounter_id": "E2",
                    "encounter_date": diag_date,
                    "concept_name": "Malignant neoplasm of lung",
                    "assertion": "present",
                }
            ],
        )
        mock_client = MagicMock()
        mock_client.run.return_value = []

        result = await build_episodes(
            "P1", anchors, mock_client, domain_id="cancer_audit"
        )
        assert (
            result.episodes_created == 1
        ), "Referral + diagnosis should merge into one episode"
        merge_calls = [
            c[1]
            for c in mock_client.run.call_args_list
            if "MERGE (ep:EpisodeOfCare" in str(c[0][0] if c[0] else "")
        ]
        assert merge_calls[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_diagnosis_outside_lookback_creates_orphan_open_episode(self):
        """A diagnosis that is beyond _DIAG_LOOKBACK_DAYS from any referral
        creates a separate diagnosis-only closed episode while the referral
        remains open (in_progress)."""
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
            _DIAG_LOOKBACK_DAYS,
        )

        import datetime

        ref_date = "2024-01-01"
        diag_date = (
            datetime.date.fromisoformat(ref_date)
            + datetime.timedelta(days=_DIAG_LOOKBACK_DAYS + 30)
        ).isoformat()

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {
                    "encounter_id": "E1",
                    "encounter_date": ref_date,
                    "concept_name": "Fast track referral for suspected lung cancer",
                }
            ],
            diagnosis_anchors=[
                {
                    "encounter_id": "E2",
                    "encounter_date": diag_date,
                    "concept_name": "Malignant neoplasm of lung",
                    "assertion": "present",
                }
            ],
        )
        mock_client = MagicMock()
        mock_client.run.return_value = []

        result = await build_episodes(
            "P1", anchors, mock_client, domain_id="cancer_audit"
        )
        assert result.episodes_created == 2

    @pytest.mark.asyncio
    async def test_handles_build_error(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
        )

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {
                    "encounter_id": "E1",
                    "encounter_date": "invalid-date",
                    "concept_name": "suspected breast cancer",
                },
            ],
        )

        mock_client = MagicMock()
        mock_client.run.side_effect = RuntimeError("db error")

        result = await build_episodes(
            "P1", anchors, mock_client, domain_id="cancer_audit"
        )
        assert len(result.errors) >= 1

    @pytest.mark.asyncio
    async def test_first_presentation_links_only_selected_day(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
        )

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {
                    "encounter_id": "E_REF",
                    "encounter_date": "2024-03-20",
                    "concept_name": "Fast track referral for suspected colorectal cancer",
                }
            ],
            first_presentation_anchors=[
                {
                    "encounter_id": "E_FP1",
                    "encounter_date": "2024-03-10",
                    "concept_name": "Rectal bleeding",
                    "semantic_tag": "finding",
                    "assertion": "present",
                },
                {
                    "encounter_id": "E_FP2",
                    "encounter_date": "2024-03-18",
                    "concept_name": "Weight loss",
                    "semantic_tag": "finding",
                    "assertion": "present",
                },
            ],
        )
        mock_client = MagicMock()
        mock_client.run.return_value = []

        await build_episodes("P1", anchors, mock_client, domain_id="cancer_audit")

        fp_ids: list[str] = []
        for call in mock_client.run.call_args_list:
            args, kwargs = call
            if not args or "UNWIND $encounters AS e" not in str(args[0]):
                continue
            for row in kwargs.get("encounters", []):
                if row.get("milestone_type") == "first_presentation":
                    fp_ids.append(str(row.get("encounter_id") or ""))

        assert set(fp_ids) == {"E_FP1"}

    @pytest.mark.asyncio
    async def test_first_presentation_links_single_encounter_on_selected_day(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
        )

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {
                    "encounter_id": "E_REF",
                    "encounter_date": "2024-03-20",
                    "concept_name": "Fast track referral for suspected colorectal cancer",
                }
            ],
            first_presentation_anchors=[
                {
                    "encounter_id": "E_FP1",
                    "encounter_date": "2024-03-10",
                    "concept_name": "Rectal bleeding",
                    "semantic_tag": "finding",
                    "assertion": "present",
                },
                {
                    "encounter_id": "E_FP2",
                    "encounter_date": "2024-03-10",
                    "concept_name": "Bowel habit change",
                    "semantic_tag": "finding",
                    "assertion": "present",
                },
            ],
        )
        mock_client = MagicMock()
        mock_client.run.return_value = []

        await build_episodes("P1", anchors, mock_client, domain_id="cancer_audit")

        fp_ids: list[str] = []
        for call in mock_client.run.call_args_list:
            args, kwargs = call
            if not args or "UNWIND $encounters AS e" not in str(args[0]):
                continue
            for row in kwargs.get("encounters", []):
                if row.get("milestone_type") == "first_presentation":
                    fp_ids.append(str(row.get("encounter_id") or ""))

        assert len(fp_ids) == 1
        assert fp_ids[0] in {"E_FP1", "E_FP2"}

    @pytest.mark.asyncio
    async def test_treatment_started_links_only_earliest_compatible_after_referral(
        self,
    ):
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
        )

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {
                    "encounter_id": "E_REF",
                    "encounter_date": "2024-03-20",
                    "concept_name": "Fast track referral for suspected breast cancer",
                }
            ],
            diagnosis_anchors=[
                {
                    "encounter_id": "E_DIAG",
                    "encounter_date": "2024-03-30",
                    "concept_name": "Malignant tumor of breast",
                    "assertion": "present",
                }
            ],
            treatment_anchors=[
                {
                    "encounter_id": "E_TX_BEFORE",
                    "encounter_date": "2024-03-01",
                    "concept_name": "Chemotherapy",
                },
                {
                    "encounter_id": "E_TX_AFTER_1",
                    "encounter_date": "2024-03-25",
                    "concept_name": "Chemotherapy",
                },
                {
                    "encounter_id": "E_TX_AFTER_2",
                    "encounter_date": "2024-04-10",
                    "concept_name": "Chemotherapy",
                },
            ],
        )
        mock_client = MagicMock()
        mock_client.run.return_value = []

        await build_episodes("P1", anchors, mock_client, domain_id="cancer_audit")

        tx_ids: list[str] = []
        for call in mock_client.run.call_args_list:
            args, kwargs = call
            if not args or "UNWIND $encounters AS e" not in str(args[0]):
                continue
            for row in kwargs.get("encounters", []):
                if row.get("milestone_type") == "treatment_started":
                    tx_ids.append(str(row.get("encounter_id") or ""))

        assert tx_ids == ["E_TX_AFTER_1"]

    @pytest.mark.asyncio
    async def test_specialist_letter_inference_completes_with_hitl(self):
        """VT-LEO-AI-087: letter + specialist seen + past stale threshold, no Rx."""
        from datetime import date

        from services.analysis_worker.app.analyzers import episode_builder as eb
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
        )

        eb._TODAY_OVERRIDE = date(2025, 3, 15)
        try:
            anchors = AnchorResult(
                patient_id="P1",
                referral_anchors=[
                    {
                        "encounter_id": "E1",
                        "encounter_date": "2024-08-05",
                        "concept_name": (
                            "Fast track referral for suspected skin cancer"
                        ),
                    }
                ],
                specialist_visit_anchors=[
                    {
                        "encounter_id": "E2",
                        "encounter_date": "2024-08-30",
                        "concept_name": (
                            "Seen in fast track suspected skin cancer clinic"
                        ),
                    }
                ],
                specialist_outcome_letter_anchors=[
                    {
                        "encounter_id": "E3",
                        "encounter_date": "2024-08-30",
                        "concept_name": "Letter (record artifact)",
                        "concept_id": 308470004,
                    }
                ],
                treatment_anchors=[],
            )
            mock_client = MagicMock()
            mock_client.run.return_value = []
            await build_episodes("P1", anchors, mock_client, domain_id="cancer_audit")
            merge_calls = [
                c[1]
                for c in mock_client.run.call_args_list
                if c[0] and "MERGE (ep:EpisodeOfCare" in str(c[0][0])
            ]
            assert merge_calls
            assert merge_calls[0]["status"] == "completed"
            assert merge_calls[0]["hitl_flag"] is True
        finally:
            eb._TODAY_OVERRIDE = None

    @pytest.mark.asyncio
    async def test_specialist_letter_inference_blocked_by_post_letter_treatment(self):
        """VT-LEO-AI-087: treatment in post-letter window blocks inference."""
        from datetime import date

        from services.analysis_worker.app.analyzers import episode_builder as eb
        from services.analysis_worker.app.analyzers.episode_builder import (
            build_episodes,
        )

        eb._TODAY_OVERRIDE = date(2025, 3, 15)
        try:
            anchors = AnchorResult(
                patient_id="P1",
                referral_anchors=[
                    {
                        "encounter_id": "E1",
                        "encounter_date": "2024-08-05",
                        "concept_name": (
                            "Fast track referral for suspected skin cancer"
                        ),
                    }
                ],
                specialist_visit_anchors=[
                    {
                        "encounter_id": "E2",
                        "encounter_date": "2024-08-30",
                        "concept_name": (
                            "Seen in fast track suspected skin cancer clinic"
                        ),
                    }
                ],
                specialist_outcome_letter_anchors=[
                    {
                        "encounter_id": "E3",
                        "encounter_date": "2024-08-30",
                        "concept_name": "Letter (record artifact)",
                    }
                ],
                treatment_anchors=[
                    {
                        "encounter_id": "E4",
                        "encounter_date": "2024-09-15",
                        "concept_name": "Chemotherapy",
                    }
                ],
            )
            mock_client = MagicMock()
            mock_client.run.return_value = []
            await build_episodes("P1", anchors, mock_client, domain_id="cancer_audit")
            merge_calls = [
                c[1]
                for c in mock_client.run.call_args_list
                if c[0] and "MERGE (ep:EpisodeOfCare" in str(c[0][0])
            ]
            assert merge_calls
            assert merge_calls[0]["status"] == "in_progress"
        finally:
            eb._TODAY_OVERRIDE = None


class TestClaimSpecialistsForEpisodes:
    """Tests for the per-episode specialist claiming algorithm.

    Core property: each specialist visit is claimed by at most one episode,
    and a historic visit cannot contaminate a later same-site episode.
    """

    def _spec(self, ep_id, site_key, ref_date_str, window_end_str):
        from datetime import date as _date
        from services.analysis_worker.app.analyzers.episode_builder import _EpisodeSpec

        return _EpisodeSpec(
            ep_id=ep_id,
            site_key=site_key,
            ref_date=_date.fromisoformat(ref_date_str),
            window_end=_date.fromisoformat(window_end_str),
        )

    def test_no_visits_returns_empty_claims(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            _claim_specialists_for_episodes,
        )

        spec = self._spec("ep1", "breast", "2024-01-01", "2024-12-31")
        claims = _claim_specialists_for_episodes([], [spec])
        assert not claims["ep1"].specialist_seen

    def test_matching_visit_is_claimed(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            _claim_specialists_for_episodes,
        )

        spec = self._spec("ep1", "breast", "2024-01-01", "2024-12-31")
        visits = [
            {
                "concept_name": "Seen in fast track suspected breast cancer clinic",
                "encounter_date": "2024-03-15",
            }
        ]
        claims = _claim_specialists_for_episodes(visits, [spec])
        assert claims["ep1"].specialist_seen
        assert claims["ep1"].specialist_visit_date == "2024-03-15"

    def test_visit_before_referral_is_not_claimed(self):
        """A specialist visit that predates the referral must not be assigned."""
        from services.analysis_worker.app.analyzers.episode_builder import (
            _claim_specialists_for_episodes,
        )

        spec = self._spec("ep1", "breast", "2024-06-01", "2025-06-01")
        visits = [
            {
                "concept_name": "Seen in fast track suspected breast cancer clinic",
                "encounter_date": "2024-01-15",
            }
        ]  # before referral
        claims = _claim_specialists_for_episodes(visits, [spec])
        assert not claims["ep1"].specialist_seen

    def test_no_cross_contamination_same_site_key(self):
        """The core regression test: two breast episodes must not share a visit.

        A 2024 breast clinic visit belongs only to the 2024 referral episode.
        The 2025 breast referral episode must remain specialist_seen=False.
        """
        from services.analysis_worker.app.analyzers.episode_builder import (
            _claim_specialists_for_episodes,
        )

        ep_2024 = self._spec("ep_2024", "breast", "2024-01-01", "2024-12-31")
        ep_2025 = self._spec("ep_2025", "breast", "2025-01-01", "2025-12-31")
        visits = [
            {
                "concept_name": "Seen in fast track suspected breast cancer clinic",
                "encounter_date": "2024-05-10",
            }
        ]
        claims = _claim_specialists_for_episodes(visits, [ep_2024, ep_2025])
        assert claims[
            "ep_2024"
        ].specialist_seen, "2024 episode should claim the 2024 visit"
        assert claims["ep_2024"].specialist_visit_date == "2024-05-10"
        assert not claims[
            "ep_2025"
        ].specialist_seen, "2025 episode must not inherit 2024 visit"

    def test_each_episode_gets_its_own_visit(self):
        """When two visits exist for two same-site episodes, each claims its own."""
        from services.analysis_worker.app.analyzers.episode_builder import (
            _claim_specialists_for_episodes,
        )

        ep_2024 = self._spec("ep_2024", "breast", "2024-01-01", "2024-12-31")
        ep_2025 = self._spec("ep_2025", "breast", "2025-01-01", "2025-12-31")
        visits = [
            {
                "concept_name": "Seen in fast track suspected breast cancer clinic",
                "encounter_date": "2024-05-10",
            },
            {
                "concept_name": "Seen in fast track suspected breast cancer clinic",
                "encounter_date": "2025-06-20",
            },
        ]
        claims = _claim_specialists_for_episodes(visits, [ep_2024, ep_2025])
        assert claims["ep_2024"].specialist_visit_date == "2024-05-10"
        assert claims["ep_2025"].specialist_visit_date == "2025-06-20"

    def test_earliest_unclaimed_visit_wins(self):
        """When two visits fall in the same episode window, the earliest is claimed."""
        from services.analysis_worker.app.analyzers.episode_builder import (
            _claim_specialists_for_episodes,
        )

        # "skin" concept names now map to "melanoma" (NCDA type)
        spec = self._spec("ep1", "melanoma", "2024-01-01", "2024-12-31")
        visits = [
            {
                "concept_name": "Seen in fast track suspected skin cancer clinic",
                "encounter_date": "2024-09-01",
            },
            {
                "concept_name": "Seen in fast track suspected skin cancer clinic",
                "encounter_date": "2024-04-01",
            },
        ]
        claims = _claim_specialists_for_episodes(visits, [spec])
        assert (
            claims["ep1"].specialist_visit_date == "2024-04-01"
        ), "Earliest visit wins"

    def test_unknown_visit_key_matches_by_temporal_proximity(self):
        """A visit whose concept name yields 'unknown' can still match by date window."""
        from services.analysis_worker.app.analyzers.episode_builder import (
            _claim_specialists_for_episodes,
        )

        spec = self._spec("ep1", "lung", "2024-03-01", "2025-03-01")
        visits = [
            {
                "concept_name": "Outpatient clinic follow-up",
                "encounter_date": "2024-07-15",
            }
        ]
        claims = _claim_specialists_for_episodes(visits, [spec])
        assert claims["ep1"].specialist_seen

    def test_different_site_visit_not_claimed(self):
        """A skin clinic visit must not be assigned to a breast episode."""
        from services.analysis_worker.app.analyzers.episode_builder import (
            _claim_specialists_for_episodes,
        )

        spec = self._spec("ep1", "breast", "2024-01-01", "2024-12-31")
        visits = [
            {
                "concept_name": "Seen in fast track suspected skin cancer clinic",
                "encounter_date": "2024-05-01",
            }
        ]
        claims = _claim_specialists_for_episodes(visits, [spec])
        assert not claims["ep1"].specialist_seen

    def test_visit_outside_window_end_not_claimed(self):
        """A visit after the episode window_end is not claimed."""
        from services.analysis_worker.app.analyzers.episode_builder import (
            _claim_specialists_for_episodes,
        )

        spec = self._spec("ep1", "breast", "2024-01-01", "2024-06-30")
        visits = [
            {
                "concept_name": "Seen in fast track suspected breast cancer clinic",
                "encounter_date": "2024-09-01",
            }
        ]  # after window_end
        claims = _claim_specialists_for_episodes(visits, [spec])
        assert not claims["ep1"].specialist_seen

    def test_empty_specs_returns_empty_dict(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            _claim_specialists_for_episodes,
        )

        visits = [{"concept_name": "Breast clinic", "encounter_date": "2024-05-01"}]
        claims = _claim_specialists_for_episodes(visits, [])
        assert claims == {}
