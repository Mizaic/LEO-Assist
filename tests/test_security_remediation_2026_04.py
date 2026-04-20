"""Static-source verification tests for the 2026-04-20 security remediation.

Each test asserts a structural invariant that must hold in the codebase to
prove a specific Phase 2 / Phase 3 fix is in place. Running these as static
checks (rather than spinning up the full app) keeps the test suite fast and
deterministic, and prevents accidental regressions if a future refactor
strips the guard.

Atlas trace: Verification Tests under DI-PLATFORM-SECURITY-BASELINE-2026-04
(see scripts/atlas/* for the full DI / DO / VT mapping).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


# ---------------------------------------------------------------------------
# Phase 2 / C2 -- terminology + fhir benchmark mutations behind verify_service_token
# ---------------------------------------------------------------------------


# State-mutating endpoints that MUST depend on verify_service_token. These
# were the specific routes called out in the Phase 2 / C2 remediation plan
# (terminology + fhir benchmark CRUD + compile/activate/rollback). Pure
# analytics POSTs (evaluate / diagnose) are intentionally not in scope here
# because they do not mutate state.
_GUARDED_MUTATIONS: list[tuple[str, str]] = [
    ("services/terminology_api/app/routers/valueset.py", "upsert_valueset"),
    ("services/terminology_api/app/routers/valueset.py", "delete_valueset"),
    ("services/terminology_api/app/routers/conceptmap.py", "upsert_conceptmap"),
    ("services/terminology_api/app/routers/conceptmap.py", "delete_conceptmap"),
    ("services/terminology_api/app/routers/guidelines.py", "compile_draft_bitmap"),
    ("services/terminology_api/app/routers/guidelines.py", "delete_scope"),
    ("services/terminology_api/app/routers/guidelines.py", "compile_bitmap"),
    ("services/terminology_api/app/routers/guidelines.py", "activate_version"),
    ("services/terminology_api/app/routers/guidelines.py", "rollback_version"),
    ("services/fhir_api/app/routers/benchmark.py", "create_benchmark_set"),
    ("services/fhir_api/app/routers/benchmark.py", "delete_benchmark_set"),
    ("services/fhir_api/app/routers/benchmark.py", "update_benchmark_value"),
    ("services/fhir_api/app/routers/benchmark.py", "delete_benchmark_value"),
    ("services/fhir_api/app/routers/benchmark.py", "upload_benchmarks"),
    ("services/fhir_api/app/routers/benchmark.py", "create_benchmark_rule"),
    ("services/fhir_api/app/routers/benchmark.py", "update_benchmark_rule"),
    ("services/fhir_api/app/routers/benchmark.py", "delete_benchmark_rule"),
    ("services/fhir_api/app/routers/benchmark.py", "run_benchmark_rule"),
]


@pytest.mark.parametrize("rel_path,fn_name", _GUARDED_MUTATIONS)
def test_mutating_endpoints_require_service_token(
    rel_path: str, fn_name: str
) -> None:
    """The named mutation must have a verify_service_token dependency above it."""
    source = _read(rel_path)
    assert "verify_service_token" in source, (
        f"{rel_path} no longer imports verify_service_token"
    )
    # Look at the decorator block immediately preceding the def. We grab
    # the 600 chars before the def; the decorator + dependencies list will
    # comfortably fit in that window.
    idx = source.find(f"def {fn_name}(")
    assert idx != -1, f"{fn_name} not found in {rel_path}"
    window = source[max(0, idx - 600) : idx]
    assert "verify_service_token" in window, (
        f"{rel_path}::{fn_name} no longer has Depends(verify_service_token); "
        "unauthenticated callers could mutate this resource"
    )


# ---------------------------------------------------------------------------
# Phase 2 / H7 -- service auth fail-closed
# ---------------------------------------------------------------------------


def test_service_auth_fails_closed_when_secret_missing() -> None:
    source = _read("libs/auth/service_auth.py")
    assert "_is_local_env" in source, "_is_local_env helper removed"
    assert "Service auth not configured" in source, (
        "verify_service_token no longer raises when the secret is unset"
    )
    assert "raise HTTPException(\n            status_code=503" in source, (
        "verify_service_token must raise HTTP 503 when not configured "
        "outside the local env"
    )


# ---------------------------------------------------------------------------
# Phase 2 / C2 -- terminology CORS rejects wildcard
# ---------------------------------------------------------------------------


def test_terminology_cors_rejects_wildcard() -> None:
    source = _read("services/terminology_api/app/main.py")
    assert "TERMINOLOGY_CORS_ORIGINS" in source
    assert "must not contain '*'" in source, (
        "terminology CORS must explicitly reject the '*' wildcard so "
        "credentialed cookies cannot be replayed by hostile origins"
    )


# ---------------------------------------------------------------------------
# Phase 2 / H4 -- prompts + model_configs admin-gated mutations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel_path,functions",
    [
        (
            "services/api/app/routers/prompts.py",
            ["create_prompt", "update_prompt", "delete_prompt", "improve_prompt"],
        ),
        (
            "services/api/app/routers/model_configs.py",
            [
                "create_model_config",
                "update_model_config",
                "delete_model_config",
                "upsert_service_config",
            ],
        ),
    ],
)
def test_admin_gated_mutations(rel_path: str, functions: list[str]) -> None:
    source = _read(rel_path)
    assert "require_admin" in source, f"{rel_path} no longer imports require_admin"
    for fn in functions:
        # Find the def line and assert require_admin is in its parameter block.
        match = re.search(
            rf"def {re.escape(fn)}\((?P<args>[^)]*)\)", source, flags=re.DOTALL
        )
        assert match, f"{fn} not found in {rel_path}"
        args = match.group("args")
        assert "require_admin" in args, (
            f"{rel_path}::{fn} no longer enforces Depends(require_admin); "
            "non-admins could mutate platform configuration"
        )


# ---------------------------------------------------------------------------
# Phase 2 / H1-H2-H3-H6 -- tenant-scoping
# ---------------------------------------------------------------------------


def test_clinician_action_requires_patient_scope() -> None:
    source = _read("services/api/app/routers/events.py")
    assert "require_patient_in_scope" in source, (
        "events.py no longer enforces tenant scope on clinician-action; "
        "any authenticated caller could submit actions against any patient"
    )
    assert "get_caller_scope_from_request" in source


def test_patient_llm_spend_scoped() -> None:
    source = _read("services/api/app/routers/model_configs.py")
    assert "require_patient_in_scope" in source
    assert "patient_llm_spend" in source
    snippet = source.split("def patient_llm_spend")[1][:1500]
    assert "require_patient_in_scope" in snippet, (
        "patient_llm_spend must call require_patient_in_scope before reading "
        "patient cost data"
    )


def test_pipeline_classification_endpoints_tenant_scoped() -> None:
    source = _read("services/api/app/routers/pipeline.py")
    # Disagreements: non-admin without patient_id is forbidden.
    assert "get_classification_disagreements" in source
    assert "require_patient_in_scope" in source, (
        "pipeline.py no longer imports require_patient_in_scope"
    )
    # Vote: must enforce tenant scope on the encounter's patient. The
    # implementation does this with an inline gp_id-in-scope.org_ids check
    # rather than the require_patient_in_scope helper, because we only have
    # the encounter id at hand.
    vote_block = source.split("def submit_classification_vote")[1][:1500]
    assert "scope.org_ids" in vote_block and "gp_id" in vote_block, (
        "submit_classification_vote must verify the encounter's GP is in the "
        "caller's org scope"
    )
    assert "scope.is_admin" in vote_block, (
        "submit_classification_vote scope check must short-circuit for admins"
    )
    # Report: admin-only.
    report_block = source.split("def get_classification_report")[1][:600]
    assert "scope.is_admin" in report_block, (
        "get_classification_report must be admin-only -- it aggregates "
        "cross-tenant classification data"
    )


def test_anchor_review_admin_only() -> None:
    source = _read("services/api/app/routers/anchor_review.py")
    assert "require_admin" in source
    # Every endpoint should depend on require_admin, not get_caller_scope.
    decorators = re.findall(r"@router\.(?:get|post|put|delete)\(.*?\)\s*async def \w+\((?P<args>[^)]*)\)", source, flags=re.DOTALL)
    assert decorators, "no router endpoints found in anchor_review.py"
    for args in decorators:
        assert "require_admin" in args, (
            "anchor_review.py endpoint missing Depends(require_admin); "
            f"args block: {args[:200]}"
        )


# ---------------------------------------------------------------------------
# Phase 2 / H5 -- sample-node allowlist + admin / service guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel_path,guard",
    [
        ("services/api/app/routers/training.py", "require_admin"),
        ("services/fhir_api/app/routers/schema.py", "verify_service_token"),
    ],
)
def test_sample_node_endpoint_locked_down(rel_path: str, guard: str) -> None:
    source = _read(rel_path)
    assert "_SAMPLE_NODE_LABEL_ALLOWLIST" in source, (
        f"{rel_path} sample-node endpoint no longer enforces a node_label allowlist"
    )
    assert "_SAMPLE_NODE_GRAPH_ALLOWLIST" in source
    assert guard in source, (
        f"{rel_path} sample-node endpoint must be gated by {guard}"
    )
    # Generic 500 detail (do not leak exception text)
    assert "sample-node lookup failed" in source, (
        f"{rel_path} no longer returns a generic error for sample-node failures"
    )


# ---------------------------------------------------------------------------
# Phase 2 / H8 -- rest_connector SSRF guard
# ---------------------------------------------------------------------------


def test_rest_connector_validates_url() -> None:
    source = _read("libs/pipeline_graph/subgraphs/rest_connector.py")
    assert "_validate_url" in source
    assert "_is_ip_safe" in source
    assert "_ALLOWED_SCHEMES" in source
    assert "is_private" in source, (
        "rest_connector SSRF guard must reject RFC1918 / private IPs after DNS"
    )
    assert "RestConnectorError" in source
    # The validation must run inside execute_rest_connector
    exec_block = source.split("def execute_rest_connector")[1][:2000]
    assert "_validate_url" in exec_block, (
        "execute_rest_connector must call _validate_url before issuing a request"
    )


# ---------------------------------------------------------------------------
# Phase 2 / H9 -- GHA workflow hardening
# ---------------------------------------------------------------------------


_PINNED_ACTIONS = {
    "actions/checkout@v4": "34e114876b0b11c390a56381ad16ebd13914f8d5",
    "actions/setup-python@v5": "a26af69be951a213d495a4c3e4e4022e16d87065",
    "actions/setup-node@v4": "49933ea5288caeca8642d1e84afbd3f7d6820020",
    "azure/login@v2": "a457da9ea143d694b1b9c7c869ebb04ebe844ef5",
}


@pytest.mark.parametrize(
    "rel_path",
    [
        ".github/workflows/cd-deploy.yml",
        ".github/workflows/ci-build.yml",
    ],
)
def test_workflows_pin_third_party_actions(rel_path: str) -> None:
    source = _read(rel_path)
    # Each used action should appear at least once with its full SHA next to
    # the @v tag in a comment so dependabot still understands the pin.
    for action_at_v, sha in _PINNED_ACTIONS.items():
        if action_at_v.split("@")[0] not in source:
            continue
        assert sha in source, (
            f"{rel_path} references {action_at_v} but the pinned commit "
            f"SHA {sha} is no longer present"
        )


def test_cd_deploy_validates_image_tag() -> None:
    source = _read(".github/workflows/cd-deploy.yml")
    # Image tag interpolation must go through env vars, not direct ${{ }} in run.
    assert re.search(r"\^\[A-Za-z0-9\._-\]\+\$", source) or "[A-Za-z0-9._-]" in source, (
        "cd-deploy.yml no longer validates image_tag against a safe-character regex"
    )


def test_ci_build_validates_base_sha() -> None:
    source = _read(".github/workflows/ci-build.yml")
    assert "BASE_SHA" in source
    assert re.search(r"\^\[0-9a-f\]\{0,40\}\$", source), (
        "ci-build.yml no longer validates BASE_SHA against a hex regex"
    )


# ---------------------------------------------------------------------------
# Phase 3 / M1 -- mail iframe sandbox + DOMPurify
# ---------------------------------------------------------------------------


def test_mail_page_sanitises_body_html() -> None:
    source = _read("services/ui/src/app/mail/page.tsx")
    assert 'import DOMPurify from "dompurify"' in source, (
        "mail/page.tsx no longer imports DOMPurify"
    )
    assert "DOMPurify.sanitize(selected.body_html" in source, (
        "mail body_html must be passed through DOMPurify before doc.write"
    )
    assert 'sandbox=""' in source, (
        "mail iframe must use sandbox=\"\" (no allow-* flags)"
    )
    assert 'referrerPolicy="no-referrer"' in source


# ---------------------------------------------------------------------------
# Phase 3 / M2 -- mission_control_encounters tenant scope
# ---------------------------------------------------------------------------


def test_mission_control_encounters_forces_org_filter() -> None:
    source = _read(
        "services/analytics_api/app/routers/mission_control_encounters.py"
    )
    assert "effective_org" in source
    # The fulltext + vector legs must both filter by effective_org, and
    # non-admin callers without an org must be rejected with 403.
    assert "Caller has no organisation scope" in source, (
        "non-admin callers without an org must be rejected before the "
        "fulltext / vector legs run"
    )


# ---------------------------------------------------------------------------
# Phase 3 / M4 -- inference reload generic error
# ---------------------------------------------------------------------------


def test_inference_reload_returns_generic_error() -> None:
    source = _read("services/api/app/routers/model_registry.py")
    reload_block = source.split("async def reload_inference")[1][:2500]
    assert "Inference service rejected the reload request" in reload_block, (
        "inference/reload no longer returns a generic 502 detail; "
        "upstream response body could leak internal paths"
    )
    assert "exc.response.text" not in reload_block, (
        "inference/reload still leaks the upstream response body to the caller"
    )


# ---------------------------------------------------------------------------
# Phase 3 / M5-M6 -- safe archive extraction
# ---------------------------------------------------------------------------


def test_trud_sync_uses_safe_zip_target() -> None:
    source = _read("services/api/app/services/trud_sync.py")
    assert "_safe_zip_target" in source
    assert ".extractall(dest_dir)" not in source, (
        "trud_sync still calls zipfile.extractall directly; archive members "
        "could escape the destination directory (Zip-Slip)"
    )


def test_model_store_uses_data_filter() -> None:
    source = _read("libs/model_store/store.py")
    has_filter = (
        "tarfile.data_filter" in source
        or 'filter="data"' in source
        or '"filter"] = "data"' in source
        or "filter='data'" in source
    )
    assert has_filter, (
        "libs/model_store/store.py no longer applies the tarfile data filter; "
        "a hostile model archive could path-traverse out of the cache dir"
    )


# ---------------------------------------------------------------------------
# Phase 3 / M7 -- docker-compose binds to loopback
# ---------------------------------------------------------------------------


def test_docker_compose_ports_bind_to_loopback() -> None:
    source = _read("docker-compose.yml")
    raw_port_lines = re.findall(r'^\s*-\s*"(\d[^"]*)"', source, flags=re.MULTILINE)
    bad = [
        line
        for line in raw_port_lines
        if not line.startswith(("127.0.0.1:", "localhost:"))
    ]
    assert not bad, (
        "docker-compose.yml has port mappings without a loopback bind: "
        f"{bad} -- this exposes seeded dev credentials to the local network"
    )


# ---------------------------------------------------------------------------
# Phase 3 / M8 -- llm_client factory does not log key hints
# ---------------------------------------------------------------------------


def test_factory_does_not_log_key_hint() -> None:
    source = _read("libs/llm_client/factory.py")
    assert "_key_hint" not in source, (
        "libs/llm_client/factory.py is back to logging a 4-char hint of the "
        "Azure OpenAI API key; this shrinks the brute-force search space"
    )
    assert "AZURE_OPENAI_API_KEY) or \"\")[-4:]" not in source
    assert "_key_status" in source, (
        "factory.py should log a configured/missing status instead of any "
        "portion of the actual key"
    )


# ---------------------------------------------------------------------------
# Phase 0 -- secrets.zip never re-introduced
# ---------------------------------------------------------------------------


def test_secrets_zip_not_in_repo() -> None:
    assert not (REPO_ROOT / "secrets.zip").exists(), (
        "secrets.zip is back in the working tree; check .gitignore and "
        "re-run the history scrub before pushing"
    )


def test_gitignore_blocks_secret_archives() -> None:
    source = _read(".gitignore")
    assert "*.zip" in source or "secrets.zip" in source, (
        ".gitignore must block secrets.zip explicitly or all *.zip files"
    )
