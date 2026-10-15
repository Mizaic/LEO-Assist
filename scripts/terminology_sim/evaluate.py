"""Score every strategy on every phrase set.

A set-mode passes when at least 95% of the codes it attaches are correct.
Among strategies where every set-mode passes, more correct codes is better.

Usage:
    python -m scripts.terminology_sim.evaluate POOLS_DIR [--detail STRATEGY]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from scripts.terminology_sim.pool import Pool, load_pools
from scripts.terminology_sim.strategies import Strategy, all_strategies

PASS_BAR = 0.95
# set name -> view: "seen" uses the pool as is; "hidden" hides the phrase.
SETS = {"labelled": "seen", "hard": "seen", "human_sf": "hidden", "real": "seen"}


@dataclass
class Tally:
    n_code: int = 0
    n_nocode: int = 0
    correct: int = 0
    wrong: int = 0
    nocode_ok: int = 0
    misses: list[str] = field(default_factory=list)

    @property
    def attached(self) -> int:
        return self.correct + self.wrong

    @property
    def precision(self) -> float:
        return self.correct / self.attached if self.attached else 1.0

    @property
    def coverage(self) -> float:
        return self.correct / self.n_code if self.n_code else 0.0


@dataclass
class View:
    name: str
    tag_mode: str
    items: list[tuple[Pool, Optional[str], Optional[Pool]]]


def _views(pools_dir: Path) -> list[View]:
    views = []
    for name, kind in SETS.items():
        path = pools_dir / f"{name}.json.gz"
        if not path.exists():
            continue
        strip_path = pools_dir / f"{name}.strip.json.gz"
        stripped = {}
        if strip_path.exists():
            stripped = {
                p.case.case_id.removesuffix("|strip"): p for p in load_pools(strip_path)
            }
        items = []
        for pool in load_pools(path):
            bare = stripped.get(pool.case.case_id)
            if kind == "hidden":
                bare = bare.hidden(pool.case.phrase) if bare else None
                pool = pool.hidden()
            items.append((pool, bare))
        for tag_mode in ("tag", "notag"):
            views.append(
                View(
                    name=name,
                    tag_mode=tag_mode,
                    items=[
                        (p, p.case.tag if tag_mode == "tag" else None, b)
                        for p, b in items
                    ],
                )
            )
    return views


def score(strategy: Strategy, view: View) -> Tally:
    tally = Tally()
    for pool, tag, bare in view.items:
        got = strategy(pool, tag, bare)
        case = pool.case
        if case.expected:
            tally.n_code += 1
            if got is None:
                continue
            if got in case.expected:
                tally.correct += 1
                continue
            tally.wrong += 1
            tally.misses.append(f"{case.phrase!r} -> {got} (want {case.expected})")
        else:
            tally.n_nocode += 1
            if got is None:
                tally.nocode_ok += 1
            else:
                tally.wrong += 1
                tally.misses.append(f"{case.phrase!r} -> {got} (want no code)")
    return tally


def _row(name: str, tallies: dict[str, Tally]) -> dict:
    return {
        "strategy": name,
        "passes": all(t.precision >= PASS_BAR for t in tallies.values()),
        "correct": sum(t.correct for t in tallies.values()),
        "wrong": sum(t.wrong for t in tallies.values()),
        "worst_precision": min(t.precision for t in tallies.values()),
        "by_view": {
            k: {
                "precision": round(t.precision, 4),
                "coverage": round(t.coverage, 4),
                "correct": t.correct,
                "wrong": t.wrong,
                "n_code": t.n_code,
                "n_nocode": t.n_nocode,
                "nocode_ok": t.nocode_ok,
            }
            for k, t in tallies.items()
        },
    }


def evaluate(pools_dir: Path) -> tuple[list[dict], dict[str, dict[str, Tally]]]:
    views = _views(pools_dir)
    rows, detail = [], {}
    for name, strategy in all_strategies().items():
        tallies = {f"{v.name}/{v.tag_mode}": score(strategy, v) for v in views}
        detail[name] = tallies
        rows.append(_row(name, tallies))
    rows.sort(key=lambda r: (not r["passes"], -r["correct"], r["wrong"]))
    return rows, detail


def _print(rows: list[dict]) -> None:
    keys = list(rows[0]["by_view"]) if rows else []
    print(
        "strategy".ljust(28),
        "pass  correct wrong ",
        " ".join(k[:16].ljust(16) for k in keys),
    )
    for r in rows:
        cells = " ".join(
            f"{v['precision']:.3f}/{v['coverage']:.2f}".ljust(16)
            for v in r["by_view"].values()
        )
        flag = "yes " if r["passes"] else "no  "
        print(
            r["strategy"].ljust(28),
            flag,
            str(r["correct"]).rjust(7),
            str(r["wrong"]).rjust(5),
            "",
            cells,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pools_dir", type=Path)
    parser.add_argument("--detail", action="append", default=[])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    rows, detail = evaluate(args.pools_dir)
    _print(rows)
    for name in args.detail:
        for view, tally in detail[name].items():
            print(f"\n== {name} {view}: {len(tally.misses)} wrong")
            for line in tally.misses:
                print("   ", line)
    if args.out:
        args.out.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
