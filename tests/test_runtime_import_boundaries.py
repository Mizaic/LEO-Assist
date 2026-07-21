from __future__ import annotations

import ast
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RUNTIME_ROOTS = (
    "libs",
    "scripts",
    "services/api",
    "services/coding_worker",
    "services/terminology_api",
)
SKIP_PARTS = {".git", ".venv", "venv", "__pycache__"}

# Subtrees excluded from Docker builds (see .dockerignore) and therefore
# never shipped in a runtime image -- exempt from this boundary check.
EXCLUDED_SUBTREES = ("scripts/archive",)


def _is_excluded(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return any(rel == sub or rel.startswith(sub + "/") for sub in EXCLUDED_SUBTREES)


def _python_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*.py")
        if path.is_file()
        and not any(part in SKIP_PARTS for part in path.parts)
        and not _is_excluded(path)
    ]


def _banned_imports(path: Path) -> list[str]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            offenders.append(node.module)
    return [name for name in offenders if name == "tests" or name.startswith("tests.")]


def test_runtime_code_does_not_import_test_packages() -> None:
    """Runtime image code must not depend on packages absent from Docker builds."""
    offenders: list[str] = []
    for root_name in RUNTIME_ROOTS:
        for path in _python_files(ROOT / root_name):
            banned = _banned_imports(path)
            offenders.extend(
                f"{path.relative_to(ROOT)} imports {module}" for module in banned
            )

    assert not offenders, "Runtime code imports test-only packages:\n" + "\n".join(
        sorted(offenders)
    )
