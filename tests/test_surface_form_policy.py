"""Tests for surface-form approval status policy."""

from __future__ import annotations

from libs.terminology.surface_form_policy import (
    cypher_resolvable_surface_form_where,
    is_resolvable_surface_form_status,
)


def test_pending_is_not_resolvable() -> None:
    assert is_resolvable_surface_form_status("pending") is False


def test_approved_and_active_are_resolvable() -> None:
    assert is_resolvable_surface_form_status("approved") is True
    assert is_resolvable_surface_form_status("active") is True


def test_deactivated_is_not_resolvable() -> None:
    assert is_resolvable_surface_form_status("deactivated") is False


def test_cypher_predicate_mentions_resolvable_statuses() -> None:
    clause = cypher_resolvable_surface_form_where("sf")
    assert "sf.status" in clause
    assert "approved" in clause
    assert "active" in clause
