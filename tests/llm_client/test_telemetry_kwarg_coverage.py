"""VT-LEO-AI-518 TC-001: every production converse call site carries
``agent_task=...``.

DI-LEO-AI-519 requires that every production call site of
``LLMClient.converse(...)`` passes a stable, snake_case ``agent_task``
literal so the telemetry events emitted by DI-LEO-AI-515 carry
meaningful task labels for cost attribution.

This test parses the Python source tree with ``ast`` and inspects every
call expression of the form ``<expr>.converse(...)``, asserting that
each such call carries an ``agent_task=...`` keyword argument.

Excluded (not LLMClient.converse):
  * ``tests/`` and ``services/*/tests/`` -- test code
  * ``scripts/`` -- one-off / out-of-band tooling
  * ``libs/llm_client/bedrock_retry.py`` -- raw boto3 client.converse
  * ``libs/llm_client/factory.py`` -- defines LLMClient.converse itself
  * ``libs/llm_client/providers.py`` -- defines invoke_with_fallback
  * ``libs/llm_client/json_helper.py`` -- defines invoke_llm_json
  * ``libs/llm_client/token_tracker.py`` -- helper module
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PRODUCTION_DIRS = [
    REPO_ROOT / "libs",
    REPO_ROOT / "services" / "api" / "app",
    REPO_ROOT / "services" / "coding_worker" / "app",
    REPO_ROOT / "services" / "analytics_api" / "app",
    REPO_ROOT / "services" / "terminology_api" / "app",
    REPO_ROOT / "services" / "analysis_worker" / "app",
    REPO_ROOT / "services" / "pipeline_worker" / "app",
]

EXCLUDED_PATHS = {
    REPO_ROOT / "libs" / "llm_client" / "bedrock_retry.py",
    REPO_ROOT / "libs" / "llm_client" / "factory.py",
    REPO_ROOT / "libs" / "llm_client" / "providers.py",
    REPO_ROOT / "libs" / "llm_client" / "json_helper.py",
    REPO_ROOT / "libs" / "llm_client" / "token_tracker.py",
}


def _iter_python_files() -> list[Path]:
    out: list[Path] = []
    for root in PRODUCTION_DIRS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if path in EXCLUDED_PATHS:
                continue
            if "tests" in path.parts or "__pycache__" in path.parts:
                continue
            out.append(path)
    return out


class _ConverseCallVisitor(ast.NodeVisitor):
    """Collect ``<expr>.converse(...)`` call sites and check each one
    carries an ``agent_task`` kwarg (or ``**kwargs`` forwarding)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.failures: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - ast API
        if isinstance(node.func, ast.Attribute) and node.func.attr == "converse":
            has_agent_task = any(
                kw.arg == "agent_task" for kw in node.keywords
            )
            has_kwargs_splat = any(kw.arg is None for kw in node.keywords)
            if not (has_agent_task or has_kwargs_splat):
                rel = self.path.relative_to(REPO_ROOT)
                self.failures.append(f"{rel}:{node.lineno} -- converse() missing agent_task")
        self.generic_visit(node)


def test_every_production_converse_call_has_agent_task_kwarg() -> None:
    failures: list[str] = []
    for path in _iter_python_files():
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (UnicodeDecodeError, SyntaxError):
            continue
        visitor = _ConverseCallVisitor(path)
        visitor.visit(tree)
        failures.extend(visitor.failures)

    assert not failures, "Production converse() call sites missing agent_task kwarg:\n  " + "\n  ".join(
        failures
    )
