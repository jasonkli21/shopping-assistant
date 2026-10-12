"""Private Personal AI transport authentication and Shopping owner mapping."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from hashlib import sha256
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from google.auth.exceptions import TransportError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from shopping.accounts.models import FirebaseOwnerBinding
from shopping.config import get_settings
from shopping.db.session import get_db

logger = logging.getLogger(__name__)
SessionDependency = Annotated[Session, Depends(get_db)]


class InvalidIdentityToken(ValueError):
    """The token is invalid or does not match the configured identity."""


class IdentityProviderUnavailable(RuntimeError):
    """Google signing certificates could not be checked."""


def _bounded_google_request_type() -> Callable[[], Any]:
    class BoundedGoogleRequest(GoogleRequest):
        def __call__(
            self,
            url: str,
            method: str = "GET",
            body: bytes | None = None,
            headers: Mapping[str, str] | None = None,
            timeout: int | float | None = 3,
            **kwargs: Any,
        ) -> Any:
            request = cast(Callable[..., Any], super().__call__)
            return request(
                url,
                method,
                body,
                headers,
                timeout=min(timeout or 3, 3),
                **kwargs,
            )

    return cast(Callable[[], Any], BoundedGoogleRequest)


def _verify_google_identity_token(token: str, *, audience: str) -> dict[str, object]:
    if not token or len(token) > 8192 or any(char.isspace() for char in token):
        raise InvalidIdentityToken
    request = _bounded_google_request_type()()
    try:
        claims = id_token.verify_oauth2_token(token, request, audience=audience)
    except TransportError as error:
        raise IdentityProviderUnavailable from error
    except Exception as error:
        raise InvalidIdentityToken from error
    finally:
        request.session.close()
    if (
        not isinstance(claims, dict)
        or claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}
        or claims.get("email_verified") is not True
    ):
        raise InvalidIdentityToken
    return claims


def _bearer_token(value: str | None) -> str:
    scheme, separator, token = (value or "").partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail={"code": "authentication_required", "message": "Sign in to continue."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


def _verify_token(token: str, *, audience: str, identity_unavailable: str) -> dict[str, object]:
    try:
        return _verify_google_identity_token(token, audience=audience)
    except InvalidIdentityToken:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Sign in again to continue."},
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except IdentityProviderUnavailable as error:
        logger.warning(
            "personal_ai_identity_verification_unavailable error_type=%s", type(error).__name__
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": identity_unavailable,
                "message": "Identity verification is temporarily unavailable.",
            },
        ) from None


def get_personal_ai_context_owner(
    request: Request,
    session: SessionDependency,
    authorization: Annotated[str | None, Header()] = None,
    user_identity_token: Annotated[str | None, Header(alias="X-User-ID-Token")] = None,
    application_id: Annotated[str | None, Header(alias="X-Application-ID")] = None,
) -> UUID:
    """Verify service and delegated user identities, then derive the configured owner."""
    settings = get_settings()
    if not settings.personal_ai_context_enabled:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "The requested resource was not found."},
        )
    if (
        settings.auth_mode != "firebase"
        or not settings.firebase_owner_uid
        or not settings.personal_ai_context_service_audience
        or not settings.personal_ai_context_service_account
        or not settings.personal_ai_context_user_audience
    ):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "integration_identity_unavailable",
                "message": "Identity verification is temporarily unavailable.",
            },
        )
    if application_id != "shopping":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "application_scope_denied",
                "message": "This application is not allowed.",
            },
        )
    if not user_identity_token or len(user_identity_token) > 8192:
        raise HTTPException(
            status_code=401,
            detail={"code": "user_identity_required", "message": "Sign in to continue."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    service_claims = _verify_token(
        _bearer_token(authorization),
        audience=settings.personal_ai_context_service_audience,
        identity_unavailable="service_identity_unavailable",
    )
    if service_claims.get("email") != settings.personal_ai_context_service_account:
        raise HTTPException(
            status_code=403,
            detail={"code": "service_identity_denied", "message": "This service is not allowed."},
        )
    user_claims = _verify_token(
        user_identity_token,
        audience=settings.personal_ai_context_user_audience,
        identity_unavailable="user_identity_unavailable",
    )
    if (
        user_claims.get("sub") != settings.personal_ai_context_google_user_subject
        or str(user_claims.get("email", "")).casefold()
        != settings.personal_ai_context_google_user_email.casefold()
        or not settings.personal_ai_context_identity_mapping_reference.strip()
    ):
        raise HTTPException(
            status_code=403,
            detail={"code": "owner_not_authorized", "message": "This account is not allowed."},
        )

    # Start one consistent, read-only transaction before resolving the fixed owner
    # binding; subsequent domain reads use the same bounded snapshot.
    connection = session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
    connection.execute(
        text("SELECT set_config('statement_timeout', :timeout, true)"),
        {"timeout": f"{int(settings.personal_ai_context_timeout_seconds * 1000)}ms"},
    )
    try:
        owner_id = session.scalar(
            select(FirebaseOwnerBinding.owner_id).where(
                FirebaseOwnerBinding.firebase_uid == settings.firebase_owner_uid
            )
        )
    except SQLAlchemyError as error:
        logger.warning(
            "personal_ai_owner_binding_lookup_failed error_type=%s", type(error).__name__
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "owner_binding_unavailable",
                "message": "The configured account is not ready for this integration.",
            },
        ) from None
    if owner_id is None or owner_id != settings.local_owner_id:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "owner_binding_unavailable",
                "message": "The configured account is not ready for this integration.",
            },
        )
    request.state.owner_key = sha256(str(owner_id).encode()).hexdigest()[:16]
    return owner_id
