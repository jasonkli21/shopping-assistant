from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shopping.api.router import router
from shopping.config import get_settings
from shopping.projects.errors import ProjectError
from shopping.projects.schemas import ApiError, ApiErrorEnvelope

settings = get_settings()

app = FastAPI(
    title="Shopping Assistant API",
    version="0.1.0",
    description="Search, discovery, research, comparison, and shortlisting API.",
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
