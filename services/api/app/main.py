"""FastAPI app for HITL training creator MVP.

Atlas trace:
  DO: DO-19FA25C3
  DI: DI-727C94B4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-19FA25C3")
"""

# aca-image: core-api build/deploy verification (no runtime effect).

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from libs.utils.logging import configure_logging, logging_context

configure_logging(service_name="core-api")

# PyRuSH uses loguru, not stdlib logging — disable its DEBUG spam
try:
    from loguru import logger as _loguru_logger

    _loguru_logger.disable("PyRuSH")
    _loguru_logger.disable("PyRuSH.PyRuSHSentencizer")
except ImportError:
    pass

import os

from app import config  # noqa: F401 - Key Vault + env before routers read secrets

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from libs.auth.org_scope import get_caller_scope
from app.deps import get_caller_scope_from_request
from app.limiter import limiter
from app.routers.admin import router as admin_router
from app.routers.admin_entra import router as admin_entra_router
from app.routers.data_quality import router as data_quality_router
from app.routers.onboarding import router as onboarding_router
from app.routers.mail_router import router as mail_router
from app.routers.anchor_review import router as anchor_review_router
from app.routers.audit import router as audit_router
from app.routers.auth import router as auth_router
from app.routers.exports import router as exports_router
from app.routers.games import router as games_router
from app.routers.operations import router as operations_router
from app.routers.model_registry import router as model_registry_router
from app.routers.devices import router as devices_router
from app.routers.presets import router as presets_router
from app.routers.training import router as training_router
from app.routers.patients import router as patients_router
from app.routers.pipeline import router as pipeline_router
from app.routers.proxy import router as proxy_router
from app.routers.review import router as review_router
from app.routers.work import router as work_router
from app.routers.terminology import router as terminology_router
from app.routers.terminology_admin import router as terminology_admin_router
from app.routers.events import router as events_router
from app.routers.prompts import router as prompts_router
from app.routers.model_configs import router as model_configs_router
from app.routers.nice_guidance import router as nice_guidance_router
from app.routers.guidance_rules import router as guidance_rules_router
from app.routers.test_patients import router as test_patients_router
from app.routers.pricing import router as pricing_router
from app.routers.lab_result_config import router as lab_result_config_router
from app.routers.ncda_pathway_config import router as ncda_pathway_config_router
from app.routers.audit_quality import router as audit_quality_router
from app.routers.sbar import router as sbar_router
from app.routers.extraction_scenarios import router as extraction_scenarios_router
from app.routers.extraction_scenario_mutations import (
    router as extraction_scenario_mutations_router,
)
from app.routers.coding_validation import router as coding_validation_router
from app.routers.validation_runs import router as validation_runs_router
from app.routers.sdk_auth import router as sdk_auth_router
from app.routers.sdk_governance import router as sdk_governance_router
from app.routers.sdk_release import router as sdk_release_router
from app.routers.sdk_telemetry import router as sdk_telemetry_router


def _validate_startup_deps():
    """Fail fast if critical dependencies are missing or unreachable."""
    import os

    # SERVICE_AUTH_SECRET: warn in non-local environments
    env = os.getenv("ENVIRONMENT", "local")
    if env != "local" and not os.getenv("SERVICE_AUTH_SECRET", ""):
        logging.getLogger(__name__).critical(
            "SECURITY: SERVICE_AUTH_SECRET is not set in %s environment. "
            "Inter-service auth is disabled.",
            env,
        )

    # LEO_LOCAL_DEV_BYPASS must never be set in a deployed environment.
    if (
        os.getenv("LEO_LOCAL_DEV_BYPASS", "").strip().lower() == "true"
        and os.getenv("ENVIRONMENT", "local").strip().lower() != "local"
    ):
        logging.getLogger(__name__).critical(
            "SECURITY: LEO_LOCAL_DEV_BYPASS=true is set in environment=%s. "
            "This flag must only be used in local development.",
            env,
        )
        raise RuntimeError(
            "LEO_LOCAL_DEV_BYPASS must not be enabled outside local environments."
        )

    # Shared knowledge graph: warn when this tier writes to a KG owned by another tier.
    deploy_env = os.getenv("LEO_DEPLOYMENT_ENVIRONMENT", "").strip()
    kg_env = os.getenv("KNOWLEDGE_GRAPH_ENVIRONMENT", "").strip()
    if deploy_env and kg_env and deploy_env != kg_env:
        logging.getLogger(__name__).warning(
            "KNOWLEDGE_GRAPH_ENVIRONMENT=%s differs from LEO_DEPLOYMENT_ENVIRONMENT=%s. "
            "Knowledge graph writes from this tier may affect other environments. "
            "Apply strict change control for guideline, terminology, and training data.",
            kg_env,
            deploy_env,
        )

    # python-jose: required for auth (JWT verification)
    try:
        from jose import jwt  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "python-jose[cryptography] is required for auth. "
            "Install it: pip install python-jose[cryptography]"
        ) from e

    # Redis: required when REDIS_URL is set (session store)
    if os.getenv("DISABLE_REDIS") not in ("true", "1"):
        url = os.getenv("REDIS_URL")
        if url:
            try:
                import redis

                client = redis.from_url(
                    url, decode_responses=True, socket_connect_timeout=5
                )
                client.ping()
                client.close()
            except ImportError as e:
                raise RuntimeError(
                    "redis is required for session store. Install it: pip install redis"
                ) from e
            except Exception as e:
                raise RuntimeError(
                    "Redis unreachable at REDIS_URL. "
                    f"Session store required for auth. Error: {e}"
                ) from e


@asynccontextmanager
async def lifespan(app: object):
    import threading

    # Lift the anyio threadpool ceiling so sync `def` endpoints (and sync I/O
    # called via `to_thread`) do not bottleneck on Starlette's default 40
    # tokens. See plan: backend-concurrency-overhaul Phase 0.
    try:
        import anyio

        _limiter = anyio.to_thread.current_default_thread_limiter()
        _tokens = int(os.getenv("ANYIO_THREADPOOL_TOKENS", "200"))
        _limiter.total_tokens = _tokens
        logging.getLogger(__name__).info("anyio threadpool ceiling set to %d", _tokens)
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Failed to lift anyio threadpool ceiling: %s", exc
        )

    _validate_startup_deps()

    from app.db.neo4j_client import PatientGraphClient
    from app.services.tenant_seed import seed_tenant_defaults

    def _tenant_seed():
        try:
            client = PatientGraphClient()
            client.initialize_schema()
            seed_tenant_defaults(client)
            client.close()
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "[Tenant] Seed failed (non-fatal): %s", exc
            )

    def _model_config_seed():
        try:
            from app.db.neo4j_client import CodingGraphClient
            from app.services.model_config_seed import seed_model_configs

            client = CodingGraphClient()
            seed_model_configs(client)
            client.close()
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "[ModelConfig] Seed failed (non-fatal): %s", exc
            )

    def _service_config_seed():
        try:
            from app.db.neo4j_client import CodingGraphClient
            from app.services.service_config_seed import seed_service_configs

            client = CodingGraphClient()
            seed_service_configs(client)
            client.close()
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "[ServiceConfig] Seed failed (non-fatal): %s", exc
            )

    def _prompt_seed():
        try:
            from scripts.seed_prompt_configs import seed_if_missing

            seed_if_missing()
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "[PromptSeed] Seed failed (non-fatal): %s", exc
            )

    def _loop_config_seed():
        try:
            from app.db.neo4j_client import PatientGraphClient
            from app.services.loop_config_seed import seed_loop_configs

            client = PatientGraphClient()
            seed_loop_configs(client)
            client.close()
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "[LoopConfig] Seed failed (non-fatal): %s", exc
            )

    def _extraction_scenario_seed():
        try:
            from app.db.neo4j_client import CodingGraphClient
            from scripts.seed_extraction_scenarios import seed_if_missing

            client = CodingGraphClient()
            seed_if_missing(client)
            client.close()
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "[ExtractionScenarioSeed] Seed failed (non-fatal): %s", exc
            )

    def _lab_result_config_seed():
        try:
            from libs.neo4j_client.client import KnowledgeGraphClient
            from scripts.seed_lab_result_config import seed_if_missing

            client = KnowledgeGraphClient()
            seed_if_missing(client)
            client.close()
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "[LabResultConfigSeed] Seed failed (non-fatal): %s", exc
            )

    t1 = threading.Thread(target=_tenant_seed, daemon=True)
    t1.start()
    t2 = threading.Thread(target=_model_config_seed, daemon=True)
    t2.start()
    t3 = threading.Thread(target=_service_config_seed, daemon=True)
    t3.start()
    t4 = threading.Thread(target=_prompt_seed, daemon=True)
    t4.start()
    t5 = threading.Thread(target=_loop_config_seed, daemon=True)
    t5.start()
    t6 = threading.Thread(target=_extraction_scenario_seed, daemon=True)
    t6.start()
    t7 = threading.Thread(target=_lab_result_config_seed, daemon=True)
    t7.start()

    def _scenario_host_seed():
        """Register the dev scenario-runner host when SCENARIO_SDK_HOST_ENABLED=1.

        This host is purely for internal validation runs (scenario panel).
        All four governance artefacts are pre-populated with dev-bypass
        placeholders so the widget token mint path succeeds without going
        through the full production onboarding flow.
        """
        if os.getenv("SCENARIO_SDK_HOST_ENABLED", "0") not in ("1", "true"):
            return
        try:
            from app.services import host_governance

            host_id = os.getenv("SCENARIO_SDK_HOST_ID", "leo-scenario-runner")
            record = host_governance.register_host(
                host_id=host_id,
                name="LEO Scenario Validation Runner",
                contact="internal@mizaic.com",
            )
            record.artefacts.update(
                {
                    "saas_embedding_agreement": "dev-bypass",
                    "dpa": "dev-bypass",
                    "dcb0129_reference": "dev-bypass",
                    "ifu_acknowledged": "dev-bypass",
                }
            )
            record.acknowledged_ifu_version = "dev-bypass"
            logging.getLogger(__name__).info(
                "[ScenarioHost] Registered scenario runner host '%s'", host_id
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "[ScenarioHost] Seed failed (non-fatal): %s", exc
            )

    t8 = threading.Thread(target=_scenario_host_seed, daemon=True)
    t8.start()

    sweeper_task = None
    if os.getenv("EXTRACTION_RUN_SWEEPER_DISABLED") not in ("1", "true"):
        try:
            from app.services.extraction_run_sweeper import run_sweeper_loop

            sweeper_task = asyncio.create_task(run_sweeper_loop())
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "[ExtractionRunSweeper] start failed (non-fatal): %s", exc
            )

    try:
        yield
    finally:
        if sweeper_task is not None and not sweeper_task.done():
            sweeper_task.cancel()
            try:
                await sweeper_task
            except (asyncio.CancelledError, Exception):
                pass


app = FastAPI(
    title="Training Creator HITL API",
    version="0.2.0",
    description="Medical-grade candidate generation and review workflow API.",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# In this API service, allow org-scope identity to come from session cookie
# (GAP-001: X-User-Email header removed as an identity source).
app.dependency_overrides[get_caller_scope] = get_caller_scope_from_request

_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
_allowed_origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "X-Request-ID",
        "X-Correlation-ID",
        "Cookie",
    ],
)

from libs.observability import ServerTimingMiddleware  # noqa: E402

app.add_middleware(ServerTimingMiddleware)


@app.middleware("http")
async def bind_request_logging_context(request: Request, call_next):
    """Bind request-level IDs into log context and echo request ID to client."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    correlation_id = request.headers.get("X-Correlation-ID") or request_id
    with logging_context(request_id=request_id, correlation_id=correlation_id):
        response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def require_xhr_for_mutations(request: Request, call_next):
    """Block cross-origin form submissions on state-changing endpoints (GAP-009).

    Browsers set X-Requested-With: XMLHttpRequest for fetch/XHR but not for
    plain form POSTs. This prevents CSRF via legacy form submissions.
    Skip for GET, HEAD, OPTIONS, and auth/OAuth routes.
    """
    safe_methods = {"GET", "HEAD", "OPTIONS"}
    skip_prefixes = ("/auth/", "/health", "/sdk/")
    path = request.url.path
    skip_xhr_paths = (
        "/api/events/lab-result",
        "/api/events/referral-response",
        "/api/events/timer",
    )
    if (
        request.method not in safe_methods
        and not any(path.startswith(p) for p in skip_prefixes)
        and path not in skip_xhr_paths
        and request.headers.get("X-Requested-With", "").lower() != "xmlhttprequest"
    ):
        return Response(
            status_code=403,
            content="CSRF check failed: X-Requested-With header required",
        )
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to every response (CSP-T-001, defence-in-depth).

    The Content-Security-Policy is restrictive: this is a JSON API, not a
    document server, so no scripts, styles, or frames should ever be served.
    """
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = (
        "max-age=63072000; includeSubDomains; preload"
    )
    return response


app.include_router(admin_router)
app.include_router(admin_entra_router)
app.include_router(onboarding_router)
app.include_router(mail_router)
app.include_router(anchor_review_router)
app.include_router(auth_router)
app.include_router(proxy_router)
app.include_router(patients_router)
app.include_router(pipeline_router)
app.include_router(review_router)
app.include_router(work_router)
app.include_router(audit_router)
app.include_router(exports_router)
app.include_router(terminology_router)
app.include_router(terminology_admin_router)
app.include_router(games_router)
app.include_router(operations_router)
app.include_router(model_registry_router)
app.include_router(devices_router)
app.include_router(presets_router)
app.include_router(training_router)
app.include_router(events_router)
app.include_router(prompts_router)
app.include_router(model_configs_router)
app.include_router(nice_guidance_router)
app.include_router(guidance_rules_router)
app.include_router(test_patients_router)
app.include_router(pricing_router)
app.include_router(lab_result_config_router)
app.include_router(ncda_pathway_config_router)
app.include_router(audit_quality_router)
app.include_router(data_quality_router)
app.include_router(sbar_router)
app.include_router(extraction_scenarios_router)
app.include_router(extraction_scenario_mutations_router)
app.include_router(coding_validation_router)
app.include_router(validation_runs_router)
app.include_router(sdk_auth_router)
app.include_router(sdk_telemetry_router)
app.include_router(sdk_release_router)
app.include_router(sdk_governance_router)


@app.get("/health")
def healthcheck():
    return {"status": "ok"}
