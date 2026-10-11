"""Shopping-owned, read-only Personal AI context endpoint."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from shopping.config import get_settings
from shopping.db.session import get_db
from shopping.integrations.personal_ai.auth import get_personal_ai_context_owner
from shopping.integrations.personal_ai.context import (
    ContextReadRequest,
    ContextReadResponse,
    read_context,
)

router = APIRouter(prefix="/v1/integrations/personal-ai", tags=["personal-ai-integration"])
SessionDependency = Annotated[Session, Depends(get_db)]
OwnerDependency = Annotated[UUID, Depends(get_personal_ai_context_owner)]


@router.post("/context", response_model=ContextReadResponse)
def read_personal_ai_context(
    request: ContextReadRequest,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> ContextReadResponse:
    """Read selected Shopping state without creating or mutating domain records."""
    settings = get_settings()
    effective_timeout = min(request.timeout_seconds, settings.personal_ai_context_timeout_seconds)
    timeout_ms = int(effective_timeout * 1000)
    try:
        connection = session.connection()
        connection.execute(
            text("SELECT set_config('statement_timeout', :timeout, true)"),
            {"timeout": f"{timeout_ms}ms"},
        )
        return read_context(session, owner_id, request)
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == "57014":
            raise HTTPException(
                status_code=504,
                detail={"code": "context_timeout", "message": "The context read timed out."},
            ) from None
        raise
