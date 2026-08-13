"""Verify referral plan order places referral_reason before compliance."""

from __future__ import annotations

import os
import sys

import pytest


def _load_plan_def(plan_id: str) -> dict:
    repo_root = os.path.join(os.path.dirname(__file__), "..")
    scripts_dir = os.path.join(repo_root, "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "seed_plan_definitions",
        os.path.join(scripts_dir, "seed_plan_definitions.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for pd in mod.PLAN_DEFINITIONS:
        if pd["id"] == plan_id:
            return pd
    raise KeyError(f"Plan '{plan_id}' not found")


def _walk_action_chain(actions: list[dict]) -> list[str]:
    by_id = {a["id"]: a for a in actions}
    successor: dict[str, str] = {}
    for action in actions:
        for rel in action.get("relatedAction") or []:
            predecessor = rel.get("actionId")
            if predecessor:
                successor[predecessor] = action["id"]
    trigger = next(
        (a for a in actions if a.get("trigger") or a.get("_nodeType") == "trigger"),
        None,
    )
    if trigger is None:
        return []
    ordered: list[str] = []
    current_id = trigger["id"]
    visited: set[str] = set()
    while current_id:
        if current_id in visited:
            break
        visited.add(current_id)
        action = by_id[current_id]
        subgraph_id = action.get("_subgraphId", "")
        if subgraph_id not in {"trigger", "durable_referral_workflow", ""}:
            ordered.append(subgraph_id)
        current_id = successor.get(current_id)
    return ordered


def test_referral_reason_precedes_compliance() -> None:
    plan = _load_plan_def("pd-referral-assessment")
    order = _walk_action_chain(plan["action"])
    reason_idx = order.index("referral_reason")
    compliance_idx = order.index("compliance")
    assert reason_idx < compliance_idx
