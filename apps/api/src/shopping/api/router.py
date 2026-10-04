from fastapi import APIRouter

from shopping.projects.router import router as projects_router

router = APIRouter()


@router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


router.include_router(projects_router)
