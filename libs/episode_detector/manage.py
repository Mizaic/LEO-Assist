"""CLI for managing per-site episode rulebooks.

Atlas trace:
  DI: DI-BF97CEAC (registry wiring)
  DI: DI-AC6838DD (gold-patient regression gate)

Examples::

    python -m libs.episode_detector.manage list --site breast
    python -m libs.episode_detector.manage register \
        --path libs/episode_detector/defaults/breast.v1.json
    python -m libs.episode_detector.manage promote \
        --site breast --version 2026.04.0
    python -m libs.episode_detector.manage rollback --site breast

The CLI defaults to the in-memory store, which is useful for dry
runs and for wiring into tests. Production deployments inject a
Neo4j-backed store via ``--store neo4j`` (not yet implemented --
this CLI stabilises the UX first; the Neo4j backend lands with the
P7 retrain loop).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from libs.episode_detector.loader import load_rulebook
from libs.episode_detector.registry import (
    InMemoryRulebookStore,
    RulebookRegistry,
    StaticGoldGate,
)


def _build_registry(args: argparse.Namespace) -> RulebookRegistry:
    """Construct the registry for CLI use.

    The CLI is a thin pass-through. If ``--gold-pass-from`` is
    provided it should point to a JSON file of ``{site_key:
    iso8601}`` entries capturing the latest VT pass per site. If
    not provided the gate is unset, which means promotion requires
    ``--force``.
    """

    store = InMemoryRulebookStore()
    gold_gate = None
    if args.gold_pass_from:
        raw = json.loads(Path(args.gold_pass_from).read_text())
        parsed = {k: datetime.fromisoformat(v) for k, v in raw.items()}
        gold_gate = StaticGoldGate(parsed)
    return RulebookRegistry(store=store, gold_gate=gold_gate)


def _cmd_register(args: argparse.Namespace) -> int:
    registry = _build_registry(args)
    rb = load_rulebook(Path(args.path))
    entry = registry.register(rb)
    _emit({"ok": True, "entry": _entry_summary(entry)})
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    registry = _build_registry(args)
    entries = registry.list_for_site(args.site)
    _emit(
        {
            "site_key": args.site,
            "entries": [_entry_summary(e) for e in entries],
        }
    )
    return 0


def _cmd_promote(args: argparse.Namespace) -> int:
    registry = _build_registry(args)
    if args.path:
        registry.register(load_rulebook(Path(args.path)))
    now = (
        datetime.fromisoformat(args.now)
        if args.now
        else datetime.now(timezone.utc)
    )
    decision = registry.promote_to_champion(
        args.site,
        args.version,
        now=now,
        force=args.force,
    )
    _emit(asdict(decision))
    return 0 if decision.promoted else 1


def _cmd_rollback(args: argparse.Namespace) -> int:
    registry = _build_registry(args)
    decision = registry.rollback(args.site)
    _emit(asdict(decision))
    return 0 if decision.promoted else 1


def _entry_summary(entry: object) -> dict:
    return {
        "site_key": getattr(entry, "site_key"),
        "rulebook_version": getattr(entry, "rulebook_version"),
        "state": getattr(entry, "state").value,
        "registered_at": getattr(entry, "registered_at").isoformat(),
        "promoted_at": (
            getattr(entry, "promoted_at").isoformat()
            if getattr(entry, "promoted_at") is not None
            else None
        ),
        "rollback_target_version": getattr(
            entry, "rollback_target_version"
        ),
    }


def _emit(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m libs.episode_detector.manage",
        description="Manage per-site episode rulebooks.",
    )
    parser.add_argument(
        "--gold-pass-from",
        type=str,
        default=None,
        help=(
            "Path to JSON file mapping site_key to ISO-8601 timestamp "
            "of the latest VT pass. Required for non-force promotion."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_reg = sub.add_parser("register", help="Register a rulebook JSON")
    p_reg.add_argument("--path", required=True)
    p_reg.set_defaults(func=_cmd_register)

    p_list = sub.add_parser("list", help="List rulebooks for a site")
    p_list.add_argument("--site", required=True)
    p_list.set_defaults(func=_cmd_list)

    p_prom = sub.add_parser("promote", help="Promote to champion")
    p_prom.add_argument("--site", required=True)
    p_prom.add_argument("--version", required=True)
    p_prom.add_argument(
        "--path", default=None, help="Optional rulebook to auto-register"
    )
    p_prom.add_argument(
        "--force",
        action="store_true",
        help="Bypass gold gate (v0 bootstrap only)",
    )
    p_prom.add_argument(
        "--now", default=None, help="Override promotion timestamp (ISO-8601)"
    )
    p_prom.set_defaults(func=_cmd_promote)

    p_rb = sub.add_parser("rollback", help="Roll back to previous champion")
    p_rb.add_argument("--site", required=True)
    p_rb.set_defaults(func=_cmd_rollback)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
