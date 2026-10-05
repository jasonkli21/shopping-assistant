from fastapi import APIRouter

from shopping.catalog.router import router as catalog_router
from shopping.comparisons.router import router as comparisons_router
from shopping.conversations.router import router as conversations_router
from shopping.evidence.router import router as evidence_router
from shopping.projects.router import router as projects_router
from shopping.research.router import router as research_router

router = APIRouter()


@router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


router.include_router(projects_router)
router.include_router(conversations_router)
router.include_router(research_router)
router.include_router(catalog_router)
router.include_router(evidence_router)
router.include_router(comparisons_router)
