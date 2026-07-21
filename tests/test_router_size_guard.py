"""Tests for scripts/router_size_guard.py (2026-07 CTO peer-review item 2
step 5: non-blocking new-router size guard).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "router_size_guard.py"

spec = importlib.util.spec_from_file_location("router_size_guard", SCRIPT)
router_size_guard = importlib.util.module_from_spec(spec)
sys.modules["router_size_guard"] = router_size_guard
spec.loader.exec_module(router_size_guard)


def _write_router(tmp_path: Path, *, n_handlers: int, n_line_padding: int) -> Path:
    lines = ["from fastapi import APIRouter", "", "router = APIRouter()", ""]
    for i in range(n_handlers):
        lines += [
            f'@router.get("/thing-{i}")',
            f"def handler_{i}():",
            "    return {}",
            "",
        ]
    lines += [f"# padding line {i}" for i in range(n_line_padding)]
    path = tmp_path / "fake_router.py"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_count_handlers_only_counts_http_method_decorators(tmp_path):
    path = _write_router(tmp_path, n_handlers=3, n_line_padding=0)
    assert router_size_guard._count_handlers(path) == 3


def test_count_handlers_ignores_non_method_router_decorators(tmp_path):
    path = tmp_path / "fake_router.py"
    path.write_text(
        "\n".join(
            [
                "router = APIRouter()",
                "@router.on_event('startup')",
                "def startup():",
                "    pass",
            ]
        ),
        encoding="utf-8",
    )
    assert router_size_guard._count_handlers(path) == 0


def test_count_loc_excludes_blank_lines(tmp_path):
    path = tmp_path / "fake_router.py"
    path.write_text("a = 1\n\n\nb = 2\n", encoding="utf-8")
    assert router_size_guard._count_loc(path) == 2


def test_oversized_router_exceeds_both_thresholds(tmp_path):
    path = _write_router(tmp_path, n_handlers=20, n_line_padding=500)
    assert router_size_guard._count_loc(path) > router_size_guard.MAX_LOC
    assert router_size_guard._count_handlers(path) > router_size_guard.MAX_HANDLERS


def test_small_router_stays_under_both_thresholds(tmp_path):
    path = _write_router(tmp_path, n_handlers=2, n_line_padding=0)
    assert router_size_guard._count_loc(path) <= router_size_guard.MAX_LOC
    assert router_size_guard._count_handlers(path) <= router_size_guard.MAX_HANDLERS


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_report_mode_lists_real_routers_and_exits_zero():
    result = _run_cli("--report")
    assert result.returncode == 0
    assert "loc" in result.stdout
    assert "services/api/app/routers/" in result.stdout


def test_cli_changed_since_unknown_ref_is_non_blocking():
    result = _run_cli("--changed-since", "not-a-real-ref-xyz")
    assert result.returncode == 0
    assert "skipping" in result.stdout.lower()


def _run_git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_changed_since_flags_a_newly_added_oversized_router(
    tmp_path, monkeypatch, capsys
):
    """Builds an isolated two-commit repo so this does not depend on real
    LEO-AI-CORE git history (which shifts over time), then points the
    module's ROOT + glob patterns at that repo to exercise the real
    end-to-end main() path."""
    repo = tmp_path / "repo"
    routers_dir = repo / "services" / "api" / "app" / "routers"
    routers_dir.mkdir(parents=True)

    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test")
    (routers_dir / "existing.py").write_text("x = 1\n", encoding="utf-8")
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-q", "-m", "base")
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    _write_router(routers_dir, n_handlers=20, n_line_padding=500)
    (routers_dir / "fake_router.py").rename(routers_dir / "new_big_router.py")
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-q", "-m", "add oversized router")

    monkeypatch.setattr(router_size_guard, "ROOT", repo)
    monkeypatch.setattr(
        router_size_guard,
        "ROUTER_DIR_GLOBS",
        ["services/api/app/routers/*.py"],
    )
    monkeypatch.setattr(
        sys, "argv", ["router_size_guard.py", "--changed-since", base_sha]
    )

    ret = router_size_guard.main()
    captured = capsys.readouterr()

    assert ret == 0
    assert "::warning" in captured.out
    assert "new_big_router.py" in captured.out
    assert "existing.py" not in captured.out
