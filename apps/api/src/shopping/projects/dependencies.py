from functools import lru_cache
from hashlib import sha256
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.config import get_settings
from shopping.db.session import get_db


@lru_cache(maxsize=4)
def _firebase_app(project_id: str):
    import firebase_admin
    from firebase_admin import credentials

    try:
        return firebase_admin.get_app("shopping-assistant")
    except ValueError:
        return firebase_admin.initialize_app(
            credentials.ApplicationDefault(),
            options={"projectId": project_id},
            name="shopping-assistant",
        )


def get_owner_id(request: Request, session: Annotated[Session, Depends(get_db)]) -> UUID:
    """Resolve the authenticated identity to a stable owner; clients never choose it."""
    settings = get_settings()
    if settings.auth_mode == "local":
        request.state.owner_key = sha256(str(settings.local_owner_id).encode()).hexdigest()[:16]
        return settings.local_owner_id

    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail={"code": "authentication_required", "message": "Sign in to continue."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        from firebase_admin import auth

        claims = auth.verify_id_token(
            token.strip(),
            app=_firebase_app(settings.firebase_project_id or ""),
            check_revoked=True,
        )
    except Exception:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Sign in again to continue."},
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    uid = claims.get("uid")
    if not isinstance(uid, str) or uid != settings.firebase_owner_uid:
        raise HTTPException(
            status_code=403,
            detail={"code": "owner_not_authorized", "message": "This account is not allowed."},
        )

    from shopping.accounts.models import FirebaseOwnerBinding

    owner_id = session.scalar(
        select(FirebaseOwnerBinding.owner_id).where(FirebaseOwnerBinding.firebase_uid == uid)
    )
    if owner_id is None or owner_id != settings.local_owner_id:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "owner_binding_unavailable",
                "message": "The configured account has not been bound to local data.",
            },
        )
    request.state.owner_key = sha256(str(owner_id).encode()).hexdigest()[:16]
    return owner_id
