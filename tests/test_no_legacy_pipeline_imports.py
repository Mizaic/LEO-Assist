from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BANNED_PATTERNS = (
    "app.services.v3.",
    "services.api.app.services.v3.",
    "app.services.v3.llm_extractor",
    "app.services.v3.coding_resolver",
    "app.services.v3.disambiguator",
    "app.services.v3.pipeline_service",
    "app.services.v3.patient_graph_writer",
    "hybrid_anchor_search",
    "/pipeline/enqueue-consensus",
    "enqueueConsensus(",
)

SKIP_PARTS = {
    ".git",
    ".next",
    "node_modules",
    "__pycache__",
    ".cursor",
    ".venv",
    "venv",
}
SCAN_ROOTS = ("services", "libs", "scripts", "tests")


def _should_scan(path: Path) -> bool:
    if any(part in SKIP_PARTS for part in path.parts):
        return False
    return path.suffix in {".py", ".md", ".ts", ".tsx"}


def test_no_legacy_pipeline_import_references() -> None:
    offenders: list[str] = []
    this_file = Path(__file__).resolve()
    for root_name in SCAN_ROOTS:
        scan_root = ROOT / root_name
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*"):
            if not path.is_file() or not _should_scan(path):
                continue
            if path.resolve() == this_file:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for pat in BANNED_PATTERNS:
                if pat in content:
                    offenders.append(f"{path.relative_to(ROOT)} :: {pat}")

    assert not offenders, "Legacy pipeline references found:\n" + "\n".join(sorted(offenders))
