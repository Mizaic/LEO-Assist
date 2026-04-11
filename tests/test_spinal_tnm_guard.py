"""VT-LEO-AI-093 -- Spinal-TNM context disambiguation guard.

Verifies that reclassify_assertion() suppresses standalone TNM-component
tokens (T0-T4, N0-N3, M0-M1) when the sentence contains spinal anatomical
or manual-therapy markers, while preserving valid cancer staging entities.

DI: DI-LEO-AI-093
Risk: R-LEO-AI-066
"""

from __future__ import annotations

import pytest

from libs.ner.scope_guard import (
    SUPPRESSED,
    is_spinal_context,
    reclassify_assertion,
)

# ---------------------------------------------------------------------------
# VT-093-TC-001 and VT-093-TC-002
# Spinal sentence with facet / mobilisation keyword -> suppressed
# ---------------------------------------------------------------------------


class TestSpinalContextSuppressed:
    def test_t4_facet_area_observable_entity(self) -> None:
        """VT-093-TC-001: T4 observable entity in facet-area sentence suppressed."""
        result = reclassify_assertion(
            entity_text="T4",
            entity_semantic_tag="observable entity",
            entity_assertion="present",
            sentence_text=(
                "right traps area palp local tenderness on rhomboids "
                "traps and stiffness C3 T4 facet areas developing a treatment plan"
            ),
        )
        assert result == SUPPRESSED

    def test_t4_staging_scale_in_mobilisation_sentence(self) -> None:
        """VT-093-TC-002: T4 staging scale entity in spinal mobilisation sentence suppressed."""
        result = reclassify_assertion(
            entity_text="T4",
            entity_semantic_tag="staging scale",
            entity_assertion="present",
            sentence_text="mobilisation of T4 facet joint performed",
        )
        assert result == SUPPRESSED

    def test_n2_radiculopathy_sentence(self) -> None:
        """VT-093-TC-003: N2 observable entity in radiculopathy sentence suppressed."""
        result = reclassify_assertion(
            entity_text="N2",
            entity_semantic_tag="observable entity",
            entity_assertion="present",
            sentence_text="cervical radiculopathy at N2 dermatome level",
        )
        assert result == SUPPRESSED

    def test_t3_nags_physiotherapy(self) -> None:
        """T3 in a NAGs physiotherapy sentence suppressed."""
        result = reclassify_assertion(
            entity_text="T3",
            entity_semantic_tag="observable entity",
            entity_assertion="present",
            sentence_text="applied NAGs at T3 and T4 levels during physiotherapy session",
        )
        assert result == SUPPRESSED

    def test_t4_snags_sentence(self) -> None:
        """T4 observable entity in SNAGs sentence suppressed."""
        result = reclassify_assertion(
            entity_text="T4",
            entity_semantic_tag="observable entity",
            entity_assertion="present",
            sentence_text="performed SNAGs C3 T4 for thoracic spine stiffness",
        )
        assert result == SUPPRESSED

    def test_m1_spondylosis_sentence(self) -> None:
        """M1 observable entity in spondylosis sentence suppressed."""
        result = reclassify_assertion(
            entity_text="M1",
            entity_semantic_tag="observable entity",
            entity_assertion="present",
            sentence_text="spondylosis at M1 level noted on MRI of spine",
        )
        assert result == SUPPRESSED

    def test_prefixed_component_pt2_vertebra_suppressed(self) -> None:
        """pT2 (pathological prefix) in vertebra sentence suppressed."""
        result = reclassify_assertion(
            entity_text="pT2",
            entity_semantic_tag="staging scale",
            entity_assertion="present",
            sentence_text="foraminal stenosis at pT2 vertebra level",
        )
        assert result == SUPPRESSED


# ---------------------------------------------------------------------------
# VT-093-TC-004 and VT-093-TC-005
# Exemptions: full triplet present, or explicit oncological context
# ---------------------------------------------------------------------------


class TestSpinalGuardExemptions:
    def test_full_tnm_triplet_exempts_suppression(self) -> None:
        """VT-093-TC-004: Full TNM triplet in sentence overrides spinal guard."""
        result = reclassify_assertion(
            entity_text="T4",
            entity_semantic_tag="staging scale",
            entity_assertion="present",
            sentence_text="colorectal cancer T4N1M0 staging confirmed at MDT",
        )
        assert result is None

    def test_oncological_context_no_spinal_marker_not_suppressed(self) -> None:
        """VT-093-TC-005: T3 in biopsy/histology context not suppressed."""
        result = reclassify_assertion(
            entity_text="T3",
            entity_semantic_tag="staging scale",
            entity_assertion="present",
            sentence_text="pT3 tumour confirmed on histology biopsy result",
        )
        assert result is None

    def test_normal_staging_sentence_not_suppressed(self) -> None:
        """Plain cancer staging sentence without spinal markers not suppressed."""
        result = reclassify_assertion(
            entity_text="T2",
            entity_semantic_tag="observable entity",
            entity_assertion="present",
            sentence_text="T2 category confirmed at oncology review",
        )
        assert result is None


# ---------------------------------------------------------------------------
# VT-093-TC-006: Non-staging entity tags not affected
# ---------------------------------------------------------------------------


class TestNonStagingTagsUnaffected:
    def test_disorder_in_spinal_context_not_suppressed_by_spinal_guard(self) -> None:
        """VT-093-TC-006: disorder tag not suppressed by spinal guard."""
        result = reclassify_assertion(
            entity_text="disc prolapse",
            entity_semantic_tag="disorder",
            entity_assertion="present",
            sentence_text="T5-6 disc prolapse confirmed on MRI of spine",
        )
        assert result is None

    def test_procedure_not_suppressed(self) -> None:
        """procedure tag in spinal sentence not suppressed by spinal guard."""
        result = reclassify_assertion(
            entity_text="spinal manipulation",
            entity_semantic_tag="procedure",
            entity_assertion="present",
            sentence_text="spinal manipulation at T3 facet performed",
        )
        assert result is None

    def test_substance_not_suppressed(self) -> None:
        """substance tag in spinal sentence not suppressed by spinal guard."""
        result = reclassify_assertion(
            entity_text="ibuprofen",
            entity_semantic_tag="substance",
            entity_assertion="present",
            sentence_text="ibuprofen prescribed for T4 facet joint pain",
        )
        assert result is None


# ---------------------------------------------------------------------------
# VT-093-TC-007: Already-reclassified assertion not affected
# ---------------------------------------------------------------------------


class TestAlreadyReclassifiedAssertionUnaffected:
    def test_absent_assertion_not_affected(self) -> None:
        """VT-093-TC-007: Absent assertion bypasses spinal guard."""
        result = reclassify_assertion(
            entity_text="T4",
            entity_semantic_tag="observable entity",
            entity_assertion="absent",
            sentence_text="no T4 facet involvement noted",
        )
        assert result is None

    def test_hypothetical_assertion_not_affected(self) -> None:
        """Hypothetical assertion bypasses spinal guard."""
        result = reclassify_assertion(
            entity_text="T4",
            entity_semantic_tag="staging scale",
            entity_assertion="hypothetical",
            sentence_text="T4 facet joint treatment planned",
        )
        assert result is None


# ---------------------------------------------------------------------------
# VT-093-TC-008 and VT-093-TC-009: is_spinal_context predicate unit tests
# ---------------------------------------------------------------------------


class TestIsSpinalContext:
    def test_nags_snags_physiotherapy_detected(self) -> None:
        """VT-093-TC-008: NAGs/SNAGs + physiotherapy sentence detected."""
        assert is_spinal_context("did NAGs C3 and SNAGs T4 in physiotherapy session")

    def test_facet_detected(self) -> None:
        """Facet joint reference detected."""
        assert is_spinal_context("pain in C3-T4 facet areas")

    def test_radiculopathy_detected(self) -> None:
        """Radiculopathy detected."""
        assert is_spinal_context("cervical radiculopathy at C6 dermatome")

    def test_vertebrae_detected(self) -> None:
        """Vertebrae reference detected."""
        assert is_spinal_context("compression of vertebrae at T5-T6")

    def test_spondylosis_detected(self) -> None:
        """Spondylosis detected."""
        assert is_spinal_context("lumbar spondylosis confirmed on X-ray")

    def test_foraminal_detected(self) -> None:
        """Foraminal stenosis detected."""
        assert is_spinal_context("foraminal stenosis at L4 level")

    def test_myelopathy_detected(self) -> None:
        """Myelopathy detected."""
        assert is_spinal_context("cervical myelopathy signs present")

    def test_oncology_sentence_not_detected(self) -> None:
        """VT-093-TC-009: Oncology sentence without spinal markers not detected."""
        assert not is_spinal_context("T4 colorectal cancer confirmed at MDT meeting")

    def test_plain_clinical_sentence_not_detected(self) -> None:
        """Standard clinical sentence without spinal markers not detected."""
        assert not is_spinal_context(
            "patient presents with hypertension and type 2 diabetes"
        )

    def test_msk_back_pain_without_spinal_markers_not_detected(self) -> None:
        """Back pain alone without explicit spinal anatomy markers not detected."""
        assert not is_spinal_context("lower back pain 3/10 on movement")
