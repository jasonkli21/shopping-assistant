import json
import logging
import re
import sys
from contextlib import asynccontextmanager
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from shopping.api.router import router
from shopping.config import get_settings
from shopping.conversations.supervisor import GenerationSupervisor
from shopping.db.session import SessionLocal
from shopping.extraction.http_retriever import HTTPPageRetriever
from shopping.integrations.personal_ai.client import UnavailablePersonalAIClient
from shopping.integrations.personal_ai.fake import FakePersonalAIClient
from shopping.projects.dependencies import _firebase_app
from shopping.projects.errors import ProjectError
from shopping.projects.schemas import ApiError, ApiErrorEnvelope
from shopping.research.supervisor import DiscoverySupervisor
from shopping.search.factory import create_search_provider

settings = get_settings()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.propagate = False


@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.disabled = False
    logger.setLevel(logging.INFO)
    if settings.auth_mode == "firebase":
        try:
            _firebase_app(settings.firebase_project_id or "")
        except Exception:
            raise RuntimeError("Firebase identity verification could not be initialized") from None
    application.state.conversation_session_factory = getattr(
        application.state, "conversation_session_factory", SessionLocal
    )
    client = getattr(application.state, "conversation_ai_client", None) or (
        FakePersonalAIClient()
        if settings.personal_ai_mode == "fake"
        else UnavailablePersonalAIClient()
    )
    supervisor = GenerationSupervisor(
        client=client,
        session_factory=application.state.conversation_session_factory,
        timeout_seconds=settings.conversation_generation_timeout_seconds,
        max_concurrent=settings.conversation_max_concurrent_generations,
    )
    application.state.generation_supervisor = supervisor
    application.state.research_session_factory = getattr(
        application.state, "research_session_factory", SessionLocal
    )
    application.state.catalog_session_factory = getattr(
        application.state, "catalog_session_factory", SessionLocal
    )
    application.state.catalog_page_retriever = (
        getattr(application.state, "catalog_page_retriever", None) or HTTPPageRetriever()
    )
    discovery_client = getattr(application.state, "discovery_ai_client", client)
    search_provider = (
        application.state.research_search_provider
        if hasattr(application.state, "research_search_provider")
        else create_search_provider(settings)
    )
    discovery = DiscoverySupervisor(
        client=discovery_client,
        search_provider=search_provider,
        session_factory=application.state.research_session_factory,
        provider_timeout_seconds=settings.research_provider_timeout_seconds,
        max_concurrent=settings.research_max_concurrent_runs,
        page_retriever=application.state.catalog_page_retriever,
    )
    application.state.discovery_supervisor = discovery
    try:
        await run_in_threadpool(supervisor.recover_after_restart)
    except SQLAlchemyError:
        # Liveness remains available while PostgreSQL is starting or migrations
        # have not yet been applied; durable routes will report storage errors.
        logger.warning("Conversation restart recovery skipped because the database is unavailable")
    supervisor.start_maintenance()
    try:
        await discovery.recover_after_restart()
    except SQLAlchemyError:
        logger.warning("Research restart recovery skipped because the database is unavailable")
    try:
        yield
    finally:
        await discovery.shutdown()
        await supervisor.shutdown()


app = FastAPI(
    title="Shopping Assistant API",
    version="0.1.0",
    description="Search, discovery, research, comparison, and shortlisting API.",
    lifespan=lifespan,
    responses={
        404: {"model": ApiErrorEnvelope, "description": "Resource not found"},
        409: {"model": ApiErrorEnvelope, "description": "Revision conflict"},
        422: {"model": ApiErrorEnvelope, "description": "Invalid request"},
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type", "X-Request-ID"],
)

app.include_router(router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    supplied_id = request.headers.get("X-Request-ID", "")
    request_id = supplied_id if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", supplied_id) else str(uuid4())
    request.state.request_id = request_id
    started_at = monotonic()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        logger.info(
            json.dumps(
                {
                    "event": "http_request_headers",
                    "request_id": request_id,
                    "owner_key": getattr(request.state, "owner_key", None),
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "header_duration_ms": round((monotonic() - started_at) * 1000),
                },
                separators=(",", ":"),
            )
        )


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details=None,
) -> JSONResponse:
    error = ApiError(
        code=code,
        message=message,
        details=details,
        request_id=getattr(request.state, "request_id", None),
    )
    payload = ApiErrorEnvelope(error=error).model_dump(exclude_none=True)
    return JSONResponse(status_code=status_code, content=payload)


@app.exception_handler(ProjectError)
async def project_error_handler(request: Request, error: ProjectError) -> JSONResponse:
    return error_response(
        request,
        status_code=error.status_code,
        code=error.code,
        message=error.message,
        details=error.details,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    details = [
        {
            "field": ".".join(str(part) for part in item["loc"]),
            "message": item["msg"],
            "code": item["type"],
        }
        for item in error.errors()
    ]
    return error_response(
        request,
        status_code=422,
        code="validation_error",
        message="Request validation failed",
        details=details,
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, error: HTTPException) -> JSONResponse:
    if isinstance(error.detail, dict):
        details = error.detail.get("details")
        code = error.detail.get("code", "request_error")
        message = error.detail.get("message", "Request failed")
    else:
        details = None
        code_by_status = {404: "not_found", 405: "method_not_allowed"}
        code = code_by_status.get(error.status_code, "request_error")
        message = str(error.detail)
    return error_response(
        request,
        status_code=error.status_code,
        code=code,
        message=message,
        details=details,
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
    original = getattr(error, "orig", None)
    if getattr(original, "sqlstate", None) == "55000":
        return error_response(
            request,
            status_code=503,
            code="owner_data_unavailable",
            message="Owner data is temporarily unavailable.",
        )
    return error_response(
        request,
        status_code=500,
        code="internal_error",
        message="An unexpected server error occurred",
    )
