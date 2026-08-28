"""The unresulted-test guard must be in the shared post-processing stack.

A guard that exists but is not wired in is worse than no guard, because the
rule file claims cover it does not give. Both the runtime pipeline and the
label verifier go through ``run_post_processing``, so wiring it here is what
makes it hold on both paths.

Atlas trace:
  DI: DI-5C9CA57B  (form markup must not become present findings)
  VT: VT-1B2063CC
"""

from __future__ import annotations

from libs.pipeline.post_processing import run_post_processing_with_trace

PANEL = """Blood Results
| FBC |  | Hb , WCC , Plts , MCV , Neut |  |  |
| Hb | 118 g/L | 23.06.26 |
"""


def _ent(text: str, label: str, last: bool = False, **kw) -> dict:
    start = PANEL.rindex(text) if last else PANEL.index(text)
    ent = {
        "text": text,
        "label": label,
        "start": start,
        "end": start + len(text),
        "assertion": "present",
    }
    ent.update(kw)
    return ent


def test_the_layer_runs_in_the_shared_stack() -> None:
    _, trace = run_post_processing_with_trace(PANEL, [])

    layer_ids = {step.get("layer_id") for step in trace}
    assert "layer_8c" in layer_ids


def test_the_layer_is_named_for_a_reader() -> None:
    _, trace = run_post_processing_with_trace(PANEL, [])

    named = {
        step.get("layer_id"): step.get("name")
        for step in trace
        if step.get("layer_id") == "layer_8c"
    }
    assert named["layer_8c"] == "Unresulted-Test Guard"


def test_a_blank_panel_row_does_not_survive_the_stack() -> None:
    entities, _ = run_post_processing_with_trace(PANEL, [_ent("FBC", "procedure")])

    assert [e["text"] for e in entities] == []


def test_a_resulted_row_survives_the_stack() -> None:
    entities, _ = run_post_processing_with_trace(
        PANEL, [_ent("Hb", "observable_entity", last=True)]
    )

    assert "Hb" in [e["text"] for e in entities]


def test_the_guard_runs_after_context_so_assertions_are_known() -> None:
    """Ordering matters: judging before ConText would read a bare default."""
    _, trace = run_post_processing_with_trace(PANEL, [])

    ids = [step.get("layer_id") for step in trace]
    context_layers = [i for i in ids if i and i.startswith("layer_7")]
    assert context_layers, "expected a ConText layer in the trace"
    assert ids.index("layer_8c") > ids.index(context_layers[-1])
