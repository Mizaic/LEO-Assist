"""Wave 6 tests for the feature flag registry."""

from __future__ import annotations

from libs.training_ext.feature_flags import FLAGS, snapshot, to_markdown


def test_every_flag_has_required_fields():
    for flag in FLAGS:
        assert flag.name, "flag must have a name"
        assert flag.wave in {0, 1, 2, 3, 4, 5}
        assert flag.description.strip(), flag.name


def test_snapshot_reports_defaults(monkeypatch):
    for flag in FLAGS:
        monkeypatch.delenv(flag.name, raising=False)
    state = snapshot()
    assert state["TRAINING_MODE"].value == "frozen"
    assert state["TRAINING_MODE"].active is True  # "frozen" is not falsy
    assert state["TRAINING_SKIP_CALIBRATION"].active is False


def test_snapshot_reflects_env_override(monkeypatch):
    monkeypatch.setenv("TRAINING_SEEDS", "1,2,3")
    state = snapshot()
    assert state["TRAINING_SEEDS"].value == "1,2,3"
    assert state["TRAINING_SEEDS"].active is True


def test_to_markdown_includes_every_flag():
    md = to_markdown()
    for flag in FLAGS:
        assert flag.name in md
        assert str(flag.wave) in md
