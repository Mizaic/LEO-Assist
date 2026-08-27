"""VT: terminology lookup maps UI shorthand observable to observable_entity."""

from libs.terminology.semantic_tag import normalise_semantic_tag


def test_observable_alias_maps_to_observable_entity():
    assert normalise_semantic_tag("observable") == "observable_entity"


def test_observation_alias_maps_to_observable_entity():
    assert normalise_semantic_tag("observation") == "observable_entity"


def test_procedure_stays_procedure():
    assert normalise_semantic_tag("procedure") == "procedure"
