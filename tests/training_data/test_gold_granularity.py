from libs.training_data.gold_granularity import (
    classify_gold_record,
    derive_sentence_records,
    split_training_windows,
)


def test_long_multisection_record_needs_split():
    text = "History: cough\nPlan: chest xray requested"
    entities = [{"text": "chest xray", "start": 21, "end": 31, "label": "PROCEDURE"}]

    result = classify_gold_record(text, entities)

    assert result.classification == "needs_split"
    assert result.safe_for_training is False


def test_empty_positive_looking_record_needs_review():
    result = classify_gold_record("PSA blood test requested", [])

    assert result.classification == "needs_review"
    assert result.safe_for_training is False


def test_short_record_with_entities_is_sentence_ok():
    text = "PSA blood test requested."
    entities = [{"text": "PSA", "start": 0, "end": 3, "label": "OBSERVABLE"}]

    result = classify_gold_record(text, entities)

    assert result.classification == "sentence_ok"
    assert result.safe_for_training is True


def test_split_training_windows_breaks_template_sections():
    text = "History: cough\nPlan: chest xray requested"

    windows = split_training_windows(text)

    assert [window.text for window in windows] == [
        "History: cough",
        "Plan: chest xray requested",
    ]


def test_derive_sentence_records_remaps_entity_offsets():
    text = "History: cough\nPlan: chest xray requested"
    start = text.index("chest xray")
    entities = [
        {"text": "chest xray", "start": start, "end": start + 10, "label": "PROCEDURE"}
    ]

    records = derive_sentence_records(
        parent_label_id="gold-1",
        parent_candidate_id="cand-1",
        text=text,
        entities=entities,
        repair_run_id="run-1",
    )

    assert len(records) == 1
    assert records[0]["text"] == "Plan: chest xray requested"
    assert records[0]["entities"][0]["start"] == records[0]["text"].index("chest xray")
    assert records[0]["entities"][0]["end"] == records[0]["entities"][0]["start"] + 10
