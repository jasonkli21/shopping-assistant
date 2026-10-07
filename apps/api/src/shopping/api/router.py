from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from shopping.accounts.models import FirebaseOwnerBinding
from shopping.accounts.router import router as accounts_router
from shopping.catalog.router import router as catalog_router
from shopping.comparisons.router import router as comparisons_router
from shopping.config import API_ROOT, get_settings
from shopping.conversations.router import router as conversations_router
from shopping.db.session import engine
from shopping.evidence.router import router as evidence_router
from shopping.preferences.router import router as preferences_router
from shopping.projects.router import router as projects_router
from shopping.research.router import router as research_router

router = APIRouter()


@router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", tags=["system"])
def readiness() -> dict[str, str]:
    """Check database reachability and that the deployed schema is at the code head."""
    try:
        migration_config = Config(str(API_ROOT / "alembic.ini"))
        expected_revision = ScriptDirectory.from_config(migration_config).get_current_head()
        with engine.connect() as connection:
            applied_revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
            settings = get_settings()
            owner_binding = None
            if settings.auth_mode == "firebase":
                owner_binding = connection.scalar(
                    select(FirebaseOwnerBinding.owner_id).where(
                        FirebaseOwnerBinding.firebase_uid == settings.firebase_owner_uid
                    )
                )
        if expected_revision is None or applied_revision != expected_revision:
            raise HTTPException(
                status_code=503,
                detail={"code": "schema_not_ready", "message": "The service is not ready."},
            )
        if settings.auth_mode == "firebase" and owner_binding != settings.local_owner_id:
            raise HTTPException(
                status_code=503,
                detail={"code": "owner_binding_not_ready", "message": "The service is not ready."},
            )
    except HTTPException:
        raise
    except (SQLAlchemyError, OSError, ValueError):
        raise HTTPException(
            status_code=503,
            detail={"code": "storage_not_ready", "message": "The service is not ready."},
        ) from None
    return {"status": "ready"}


router.include_router(projects_router)
router.include_router(preferences_router)
router.include_router(conversations_router)
router.include_router(research_router)
router.include_router(catalog_router)
router.include_router(evidence_router)
router.include_router(comparisons_router)
router.include_router(accounts_router)
