"""Work preview chips for Validation Lab inspector spans."""

from libs.validation_lab.work_preview import (
    compact_inspector_payload,
    stage_work_preview,
)


def test_work_preview_lists_facts() -> None:
    preview = stage_work_preview(
        {"entities": [{"text": "dysphagia"}, {"text": "weight loss"}]}
    )
    assert "2 facts" in preview["headline"]
    assert [item["text"] for item in preview["items"]] == [
        "dysphagia",
        "weight loss",
    ]


def test_work_preview_says_zero_facts_when_entities_empty() -> None:
    preview = stage_work_preview({"entities": []})
    assert preview["headline"] == "Found 0 facts"
    assert preview["items"] == []


def test_work_preview_lists_codes() -> None:
    preview = stage_work_preview(
        {"entities": [{"text": "dysphagia", "concept_id": "40739000"}]}
    )
    assert "Coded 1" in preview["headline"]
    assert preview["items"][0]["code"] == "40739000"


def test_work_preview_summarises_sbar_sections() -> None:
    preview = stage_work_preview(
        {
            "sbar_report": {
                "situation": "Urgent upper GI referral.",
                "background": "",
                "assessment": "",
                "recommendation": "",
            }
        }
    )
    assert "1 of 4" in preview["headline"]
    assert preview["items"][0]["text"].startswith("situation:")


def test_work_preview_reads_nested_snomed_code() -> None:
    preview = stage_work_preview(
        {
            "entities": [
                {
                    "text": "dysphagia",
                    "coding": {"snomed_concept_id": "40739000"},
                }
            ]
        }
    )
    assert preview["items"][0]["code"] == "40739000"


def test_compact_payload_keeps_fact_codes() -> None:
    compact = compact_inspector_payload(
        {
            "entities": [
                {
                    "text": "dysphagia",
                    "concept_id": "40739000",
                    "evidence": "dysphagia",
                    "evidence_sentence": "Reports progressive dysphagia.",
                    "offsets": [0, 9],
                    "raw": "x" * 200,
                }
            ],
            "encounter_text": "x" * 4000,
        }
    )
    assert compact["entities"][0]["text"] == "dysphagia"
    assert compact["entities"][0]["concept_id"] == "40739000"
    assert compact["entities"][0]["evidence"] == "dysphagia"
    assert compact["entities"][0]["evidence_sentence"] == (
        "Reports progressive dysphagia."
    )
    assert "offsets" not in compact["entities"][0]
    assert len(compact["encounter_text"]) < 4000


def test_work_preview_keeps_documents_evidence_fields() -> None:
    preview = stage_work_preview(
        {
            "entities": [
                {
                    "text": "dysphagia",
                    "concept_id": "40739000",
                    "evidence": "dysphagia",
                    "__sentence_id": "s-1",
                }
            ],
            "sentences": [
                {
                    "sentence_id": "s-1",
                    "text": "Reports progressive dysphagia for 6 weeks.",
                }
            ],
        }
    )
    item = preview["items"][0]
    assert item["evidence"] == "dysphagia"
    assert item["evidenceSentence"] == ("Reports progressive dysphagia for 6 weeks.")
