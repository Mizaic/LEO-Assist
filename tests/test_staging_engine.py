from libs.staging.engine import StagingRulesEngine


def _engine() -> StagingRulesEngine:
    engine = StagingRulesEngine()
    engine.load_rules()
    return engine


def test_explicit_stage_has_priority_over_tnm() -> None:
    engine = _engine()
    result = engine.resolve_stage(
        cancer_type_snomed="254837009",  # breast
        tnm="T4N3M1",
        explicit_stage="Stage II",
        source="coded",
    )
    assert result.cancer_stage == "early"
    assert result.staging_system == "explicit_stage"


def test_derives_stage_from_tnm_when_no_explicit() -> None:
    engine = _engine()
    result = engine.resolve_stage(
        cancer_type_snomed="254837009",  # breast
        tnm="T1N0M0",
        explicit_stage=None,
        source="coded",
    )
    assert result.staging_system == "TNM"
    assert result.cancer_stage in {"early", "late", "unknown"}


def test_non_tnm_system_mapping_ann_arbor() -> None:
    engine = _engine()
    result = engine.resolve_stage(
        cancer_type_snomed="363495004",
        explicit_stage="Ann Arbor stage III",
        source="coded",
    )
    assert result.staging_system == "Ann Arbor"
    assert result.cancer_stage == "late"


def test_unknown_when_no_evidence() -> None:
    engine = _engine()
    result = engine.resolve_stage(
        cancer_type_snomed="310504009",
        explicit_stage=None,
        tnm=None,
        source="text_scan",
    )
    assert result.cancer_stage == "unknown"
    assert result.staging_source == "none"
