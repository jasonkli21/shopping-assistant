import logging
from contextlib import asynccontextmanager
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
from shopping.projects.errors import ProjectError
from shopping.projects.schemas import ApiError, ApiErrorEnvelope
from shopping.research.supervisor import DiscoverySupervisor
from shopping.search.factory import create_search_provider

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.conversation_session_factory = getattr(
        application.state, "conversation_session_factory", SessionLocal
    )
    client = (
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


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
async def unexpected_error_handler(request: Request, _error: Exception) -> JSONResponse:
    return error_response(
        request,
        status_code=500,
        code="internal_error",
        message="An unexpected server error occurred",
    )
