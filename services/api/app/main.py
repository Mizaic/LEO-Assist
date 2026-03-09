"""FastAPI app for HITL training creator MVP."""

from __future__ import annotations

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

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from libs.auth.org_scope import get_caller_scope

from app import config  # noqa: F401 - loads secrets/.env
from app.deps import get_caller_scope_from_request

limiter = Limiter(key_func=get_remote_address)
from app.routers.admin import router as admin_router
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
from app.routers.terminology import router as terminology_router
from app.routers.terminology_admin import router as terminology_admin_router
from app.routers.events import router as events_router
from app.routers.prompts import router as prompts_router
from app.routers.model_configs import router as model_configs_router
from app.routers.nice_guidance import router as nice_guidance_router
from app.routers.guidance_rules import router as guidance_rules_router
from app.routers.pricing import router as pricing_router


def _validate_startup_deps():
    """Fail fast if critical dependencies are missing or unreachable."""
    import os

    # python-jose: required for auth (JWT verification)
    try:
        from jose import jwt  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "python-jose[cryptography] is required for auth. Install it: pip install python-jose[cryptography]"
        ) from e

    # Redis: required when REDIS_URL is set (session store)
    if os.getenv("DISABLE_REDIS") not in ("true", "1"):
        url = os.getenv("REDIS_URL")
        if url:
            try:
                import redis
                client = redis.from_url(url, decode_responses=True, socket_connect_timeout=5)
                client.ping()
                client.close()
            except ImportError as e:
                raise RuntimeError(
                    "redis is required for session store. Install it: pip install redis"
                ) from e
            except Exception as e:
                raise RuntimeError(
                    f"Redis unreachable at REDIS_URL. Session store required for auth. Error: {e}"
                ) from e


@asynccontextmanager
async def lifespan(app: object):
    import threading

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

    t1 = threading.Thread(target=_tenant_seed, daemon=True)
    t1.start()
    t2 = threading.Thread(target=_model_config_seed, daemon=True)
    t2.start()
    t3 = threading.Thread(target=_service_config_seed, daemon=True)
    t3.start()
    t4 = threading.Thread(target=_prompt_seed, daemon=True)
    t4.start()
    yield


app = FastAPI(
    title="Training Creator HITL API",
    version="0.2.0",
    description="Medical-grade candidate generation and review workflow API.",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    skip_prefixes = ("/auth/", "/health")
    if (
        request.method not in safe_methods
        and not any(request.url.path.startswith(p) for p in skip_prefixes)
        and request.headers.get("X-Requested-With", "").lower() != "xmlhttprequest"
    ):
        return Response(status_code=403, content="CSRF check failed: X-Requested-With header required")
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
app.include_router(onboarding_router)
app.include_router(mail_router)
app.include_router(anchor_review_router)
app.include_router(auth_router)
app.include_router(proxy_router)
app.include_router(patients_router)
app.include_router(pipeline_router)
app.include_router(review_router)
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
app.include_router(pricing_router)


@app.get("/health")
def healthcheck():
    return {"status": "ok"}
