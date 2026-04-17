"""Assign UN -> batch labels and rewrite the DI inventory + README."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AUDITS = REPO / "design-controls" / "audits"

BATCH_PLAN: list[tuple[str, list[str], str]] = [
    (
        "01",
        ["UN-0374FE26"],
        "SNOMED auto-coding core (8 new DIs + existing pipeline DIs)",
    ),
    ("02", ["UN-B2C85448"], "Entity provenance and immutable source linking"),
    ("03", ["UN-06388412"], "ConText assertion rule maintenance"),
    ("04", ["UN-14FA847A"], "Multi-label NER classification"),
    ("05", ["UN-83D9A46D"], "Ontology-grounded relation linking"),
    ("06", ["UN-1AC15812"], "Training-label audit with safe auto-fix"),
    ("07", ["UN-AE5B5691"], "Canary NER rollout with regression halt"),
    ("08", ["UN-B9FDC3CA"], "Surface form dictionary maintenance"),
    ("09", ["UN-4AEB2F29"], "SNOMED release alignment and diffing"),
    ("10", ["UN-7D740697"], "Coding correction reviewer workspace"),
    ("11", ["UN-55011459"], "Clinical review queue"),
    ("12", ["UN-8663A98C"], "Encounter classification management"),
    (
        "13",
        [
            "UN-6C8AEB83",
            "UN-AFFA1FB3",
            "UN-575E8DCB",
            "UN-459367FA",
            "UN-06FD3F7D",
            "UN-A949A642",
            "UN-87632C9E",
            "UN-AE5D7812",
        ],
        "Override analytics, SBAR, interpretation, completeness, quality monitoring",
    ),
    (
        "14",
        [
            "UN-FC99D533",
            "UN-2C01CF40",
            "UN-5C67AAD9",
            "UN-D92EB141",
            "UN-9206EFF0",
            "UN-9396A2FA",
            "UN-2266BDAE",
            "UN-67663AAF",
            "UN-1A6F1E0E",
            "UN-F3300833",
            "UN-6D46C832",
            "UN-FBBFD5CB",
        ],
        "Pathway, referral, episode, decision support",
    ),
    (
        "15",
        [
            "UN-8659DD53",
            "UN-F6A0C5BA",
            "UN-ED00ED74",
            "UN-EA93F7B7",
            "UN-17724530",
            "UN-785DFCDE",
            "UN-412D1ECD",
            "UN-A031A603",
            "UN-C2F187E9",
            "UN-F8E1F0D0",
            "UN-2C6E6933",
            "UN-4BD56518",
            "UN-F2372DE0",
            "UN-9A7C2AA3",
            "UN-21D88B69",
            "UN-9E66C163",
            "UN-4DCD5891",
            "UN-7294050B",
            "UN-16116C5F",
            "UN-3376B57D",
            "UN-FB2DA651",
            "UN-16E151CB",
            "UN-718B7AF3",
            "UN-94833CA3",
            "UN-BB817C74",
            "UN-B70ACD96",
            "UN-9396A2FA",
            "UN-299200A0",
            "UN-E8A5B04A",
            "UN-E6195868",
            "UN-407F090F",
            "UN-A412610D",
            "UN-319F33F0",
            "UN-87CB1498",
            "UN-12EEF12D",
            "UN-06FDC315",
            "UN-70A35225",
            "UN-5236129E",
            "UN-07AB5B97",
            "UN-395B630E",
            "UN-66396DEA",
            "UN-47B82B96",
        ],
        "Change mgmt, approvals, RBAC, security, auth, data protection, ops, KB, misc",
    ),
]


def load_un_index() -> dict[str, dict]:
    return json.loads((AUDITS / "un-index.json").read_text(encoding="utf-8"))


def assign_batch_to_un(
    un_index: dict[str, dict],
) -> tuple[dict[str, str], dict[str, str]]:
    un_to_batch: dict[str, str] = {}
    un_to_theme: dict[str, str] = {}
    for batch_id, uns, theme in BATCH_PLAN:
        for un in uns:
            un_to_batch.setdefault(un, batch_id)
            un_to_theme.setdefault(un, theme)

    for un_id in un_index:
        if un_id not in un_to_batch:
            un_to_batch[un_id] = "15"
            un_to_theme[un_id] = (
                "Change mgmt, approvals, RBAC, security, auth, data protection, "
                "ops, KB, misc"
            )
    return un_to_batch, un_to_theme


def update_inventory_csv(
    un_to_batch: dict[str, str],
    un_index: dict[str, dict],
) -> dict[str, int]:
    path = AUDITS / "di-inventory.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    batch_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        un_id = row["parent_un_id"]
        batch = un_to_batch.get(un_id, "15")
        row["proposed_batch"] = batch
        batch_counts[batch] += 1
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return dict(batch_counts)


def _batch_row(
    batch_id: str,
    theme: str,
    uns: list[str],
    un_index: dict[str, dict],
    batch_counts: dict[str, int],
) -> str:
    di_count = batch_counts.get(batch_id, 0)
    un_count = len(uns)
    return (
        f"| Phase {batch_id} | {theme} | {un_count} | {di_count} | pending | "
        "n/a |"
    )


def write_readme(
    un_to_batch: dict[str, str],
    un_to_theme: dict[str, str],
    un_index: dict[str, dict],
    batch_counts: dict[str, int],
) -> None:
    batch_to_uns: dict[str, list[str]] = defaultdict(list)
    for un_id, batch in un_to_batch.items():
        batch_to_uns[batch].append(un_id)
    for ids in batch_to_uns.values():
        ids.sort()

    lines: list[str] = []
    lines += [
        "# Design Controls - Retrospective DI Audit",
        "",
        ("This directory holds the batched retrospective audit of every "
         "Design Input (DI) currently registered in Atlas under product "
         "`PROD-LEO-CORE-AI-20260415-6AE8A23B`."),
        "",
        ("Goal: locate the implementation for each DI, assess it against the "
         "code-quality rules and acceptance criteria, close meaningful gaps "
         "via targeted code changes, and complete the Atlas paperwork (new "
         "DOs, amended DIs, new DIs for reverse gaps, new VTs, link edges)."),
        "",
        "## Inventory snapshot",
        "",
        f"- User Needs with DIs: {len(un_index)}",
        f"- Total DIs audited: {sum(batch_counts.values())}",
        f"- Phases: {len(BATCH_PLAN)}",
        "",
        "## Batch composition",
        "",
        "| Phase | Theme | UNs | DIs | Status | Report |",
        "|---|---|---|---|---|---|",
    ]
    for batch_id, uns, theme in BATCH_PLAN:
        report = f"[batch-{batch_id}.md](batch-{batch_id}.md)"
        di_count = batch_counts.get(batch_id, 0)
        lines.append(
            f"| Phase {batch_id} | {theme} | {len(uns)} | {di_count} | "
            f"pending | {report} |"
        )

    lines += [
        "",
        "## Per-batch UN roster",
        "",
    ]
    for batch_id, uns, theme in BATCH_PLAN:
        lines.append(f"### Phase {batch_id} - {theme}")
        lines.append("")
        lines.append("| UN ID | DI count | Title |")
        lines.append("|---|---|---|")
        uns_in_batch = sorted(batch_to_uns.get(batch_id, []))
        for un_id in uns_in_batch:
            meta = un_index.get(un_id, {})
            title = (meta.get("title") or "").replace("|", "\\|")
            if len(title) > 110:
                title = title[:107] + "..."
            lines.append(f"| {un_id} | {meta.get('di_count', 0)} | {title} |")
        lines.append("")

    lines += [
        "## Files",
        "",
        "- `di-inventory.csv` - authoritative DI roster. Updated cumulatively "
        "as each batch lands.",
        "- `un-index.json` - UN -> DI map generated from the Atlas trace "
        "matrix (`get_traceability_matrix`).",
        "- `atlas-summary.md` - high-level DI counts per UN.",
        "- `improvements-backlog.md` - anything deferred during a batch gate.",
        "- `batch-NN.md` - per-batch report with verdict, improvements, and "
        "Atlas mutations per DI.",
        "",
        "## Rules followed",
        "",
        "- `.cursor/rules/code-quality.mdc` (function/file/complexity/nesting "
        "limits)",
        "- `.cursor/rules/dual-path-consistency.mdc` (unified pipeline + "
        "Ask LEO parity)",
        "- `.cursor/rules/design-controls-first.mdc` (DI -> DO -> VT -> Risk "
        "traceability)",
        "- `.cursor/rules/vt-enforcement.mdc` (VT creation and link discipline)",
        "- `.cursor/rules/ascii-only.mdc`",
    ]

    (AUDITS / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_backlog_stub() -> None:
    path = AUDITS / "improvements-backlog.md"
    if path.exists():
        return
    content = (
        "# Improvements backlog\n"
        "\n"
        "Anything deferred during a per-batch gate ends up here.\n"
        "\n"
        "| Date | Phase | DI | Severity | Description | Owner | Status |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    path.write_text(content, encoding="utf-8")


def main() -> None:
    un_index = load_un_index()
    un_to_batch, un_to_theme = assign_batch_to_un(un_index)
    batch_counts = update_inventory_csv(un_to_batch, un_index)
    write_readme(un_to_batch, un_to_theme, un_index, batch_counts)
    write_backlog_stub()
    print("Batch counts:")
    for batch_id, _, theme in BATCH_PLAN:
        print(f"  Phase {batch_id}: {batch_counts.get(batch_id, 0)} DIs - {theme}")


if __name__ == "__main__":
    main()
