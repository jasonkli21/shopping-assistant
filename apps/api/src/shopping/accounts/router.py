from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shopping.accounts.export import OwnerDataLimitExceeded, export_owner_data, purge_owner_data
from shopping.db.session import get_db
from shopping.projects.dependencies import get_owner_id

router = APIRouter(prefix="/account", tags=["account"])
SessionDependency = Annotated[Session, Depends(get_db)]
OwnerDependency = Annotated[UUID, Depends(get_owner_id)]


class OwnerPurgeResult(BaseModel):
    status: Literal["purged"]
    deleted_records: dict[str, int]
    audit_retained: bool = True


@router.get("/export", response_class=Response)
def export_account_data(session: SessionDependency, owner_id: OwnerDependency) -> Response:
    """Download a bounded, owner-scoped JSON export with no raw retrieved page text."""
    try:
        payload = export_owner_data(session, owner_id)
    except OwnerDataLimitExceeded as error:
        raise HTTPException(
            status_code=413,
            detail={"code": "export_limit", "message": str(error)},
        ) from None
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="shopping-assistant-export.json"'},
    )


@router.delete("/data", response_model=OwnerPurgeResult)
def purge_account_data(
    session: SessionDependency,
    owner_id: OwnerDependency,
    confirm: Annotated[Literal["DELETE_MY_DATA"], Query()],
) -> OwnerPurgeResult:
    """Delete owner data after an explicit confirmation and retain only a count audit."""
    del confirm
    try:
        deleted_records = purge_owner_data(session, owner_id)
    except OwnerDataLimitExceeded as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "purge_limit", "message": str(error)},
        ) from None
    return OwnerPurgeResult(status="purged", deleted_records=deleted_records)
