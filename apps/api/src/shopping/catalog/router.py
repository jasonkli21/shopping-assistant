from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from shopping.catalog import commands, reads
from shopping.catalog.schemas import (
    CatalogCorrectionCommand,
    CatalogCorrectionRead,
    CatalogCorrectionRevertCommand,
    CatalogNormalizationRead,
    CatalogVariantChoicePage,
    NormalizeCandidateCommand,
    OfferPage,
    ProductRead,
    ProjectProductPage,
)
from shopping.db.session import get_db
from shopping.extraction.http_retriever import HTTPPageRetriever
from shopping.extraction.retriever import PageRetrievalError
from shopping.extraction.task import (
    CatalogExtractionError,
    StructuredDataCatalogExtractionTask,
)
from shopping.projects.dependencies import get_owner_id

router = APIRouter(tags=["catalog"])
SessionDependency = Annotated[Session, Depends(get_db)]
OwnerDependency = Annotated[UUID, Depends(get_owner_id)]


async def _with_session(request: Request, operation: Callable[[Session], object]):
    factory = request.app.state.catalog_session_factory

    def call():
        with factory() as session:
            return operation(session)

    worker = asyncio.create_task(asyncio.to_thread(call))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        try:
            await worker
        except Exception:
            pass
        raise


def _retriever(request: Request):
    return getattr(request.app.state, "catalog_page_retriever", None) or HTTPPageRetriever()


def _extraction_task(request: Request):
    return getattr(request.app.state, "catalog_extraction_task", None) or (
        StructuredDataCatalogExtractionTask()
    )


@router.post(
    "/projects/{project_id}/candidates/{candidate_id}/normalize",
    response_model=CatalogNormalizationRead,
    responses={
        404: {"description": "Candidate not found"},
        409: {"description": "Version conflict"},
    },
)
async def normalize_candidate(
    project_id: UUID,
    candidate_id: UUID,
    command: NormalizeCandidateCommand,
    request: Request,
    owner_id: OwnerDependency,
) -> CatalogNormalizationRead:
    replay, requested_url = await _with_session(
        request,
        lambda session: commands.normalization_preflight(
            session, owner_id, project_id, candidate_id, command
        ),
    )
    if replay is not None:
        return replay
    assert requested_url is not None

    document = None
    extraction = None
    failure_code = None
    failure_status = None
    try:
        document = await _retriever(request).retrieve(requested_url)
    except PageRetrievalError as error:
        failure_code = error.code
        if error.code.startswith("blocked_") or error.code in {"invalid_url", "redirect_limit"}:
            failure_status = "blocked"
        elif error.code == "unsupported_content_type":
            failure_status = "unsupported"
        else:
            failure_status = "failed"
    except Exception:
        failure_code, failure_status = "retrieval_failed", "failed"

    if document is not None:
        try:
            extraction = await _extraction_task(request).extract(document)
        except CatalogExtractionError as error:
            failure_code = error.code
            failure_status = "unsupported"
        except Exception:
            failure_code = "extraction_failed"
            failure_status = "failed"

    return await _with_session(
        request,
        lambda session: commands.complete_normalization(
            session,
            owner_id=owner_id,
            project_id=project_id,
            candidate_id=candidate_id,
            command=command,
            document=document,
            extraction=extraction,
            failure_code=failure_code,
            failure_status=failure_status,
        ),
    )


@router.post(
    "/projects/{project_id}/candidates/{candidate_id}/correction",
    response_model=CatalogCorrectionRead,
)
def correct_candidate(
    project_id: UUID,
    candidate_id: UUID,
    command: CatalogCorrectionCommand,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> CatalogCorrectionRead:
    replay = commands.exact_correction_replay(session, owner_id, project_id, candidate_id, command)
    if replay is not None:
        return replay
    return commands.correct_candidate(
        session,
        owner_id=owner_id,
        project_id=project_id,
        candidate_id=candidate_id,
        command=command,
    )


@router.post(
    "/projects/{project_id}/candidates/{candidate_id}/correction/revert",
    response_model=CatalogCorrectionRead,
)
def revert_candidate_correction(
    project_id: UUID,
    candidate_id: UUID,
    command: CatalogCorrectionRevertCommand,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> CatalogCorrectionRead:
    replay = commands.exact_correction_replay(session, owner_id, project_id, candidate_id, command)
    if replay is not None:
        return replay
    return commands.revert_candidate_correction(
        session,
        owner_id=owner_id,
        project_id=project_id,
        candidate_id=candidate_id,
        command=command,
    )


@router.get("/projects/{project_id}/products", response_model=ProjectProductPage)
def list_project_products(
    project_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> ProjectProductPage:
    return reads.list_project_products(session, owner_id, project_id, limit=limit, cursor=cursor)


@router.get("/products/{product_id}", response_model=ProductRead)
def get_product(
    product_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> ProductRead:
    return reads.get_product(session, owner_id, product_id)


@router.get("/products", response_model=CatalogVariantChoicePage)
def list_catalog_variants(
    session: SessionDependency,
    owner_id: OwnerDependency,
    q: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> CatalogVariantChoicePage:
    return reads.list_catalog_variants(session, owner_id, query=q, limit=limit, cursor=cursor)


@router.get("/products/{product_id}/offers", response_model=OfferPage)
def list_product_offers(
    product_id: UUID,
    session: SessionDependency,
    owner_id: OwnerDependency,
    variant_id: Annotated[UUID, Query()],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> OfferPage:
    return reads.list_product_offers(
        session,
        owner_id,
        product_id,
        variant_id,
        limit=limit,
        cursor=cursor,
    )
