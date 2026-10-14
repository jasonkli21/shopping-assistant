"""Private service plus request-bound user identity for delegated Shopping writes."""

from __future__ import annotations

import base64
import time
from hashlib import sha256
from uuid import UUID

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import HTTPException, Request
from google.oauth2 import id_token
from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.accounts.models import FirebaseOwnerBinding
from shopping.config import Settings
from shopping.integrations.personal_ai.auth import (
    _bearer_token,
    _bounded_google_request_type,
    _verify_token,
)
from shopping.integrations.personal_ai.task_wire import (
    TARGET_CONTRACT_FINGERPRINT,
    TASK_CONTRACT_FINGERPRINT,
    DelegatedTaskRequest,
    verify_delegated_user,
)

GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})


def task_owner(
    request: Request, body: dict, session: Session, settings: Settings
) -> tuple[UUID, str]:
    """Resolve the explicit linked domain owner; no email or UUID-based linking."""
    expected_contract = (
        TARGET_CONTRACT_FINGERPRINT
        if body.get("schema_version") == "suite-task-target-v1"
        else TASK_CONTRACT_FINGERPRINT
    )
    if request.headers.get("x-task-contract-fingerprint") != expected_contract:
        raise HTTPException(409, "task_contract_incompatible")
    service = _verify_token(
        _bearer_token(request.headers.get("authorization")),
        audience=settings.personal_ai_context_service_audience,
        identity_unavailable="service_identity_unavailable",
    )
    if service.get("email") != settings.personal_ai_context_service_account:
        raise HTTPException(403, "service_identity_denied")
    try:
        encoded = settings.personal_ai_tasks_delegation_public_key
        public = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        )
        identity = verify_delegated_user(
            request.headers.get("x-user-delegation", ""),
            body,
            public_key=public,
            issuer=settings.personal_ai_tasks_delegation_issuer,
            audience=settings.personal_ai_context_service_audience,
            key_id=settings.personal_ai_tasks_delegation_key_id,
            now=int(time.time()),
            allowed_user_issuers=GOOGLE_ISSUERS,
        )
    except ValueError as error:
        raise HTTPException(401, "delegated_user_invalid") from error
    if (
        identity.subject != settings.personal_ai_context_google_user_subject
        or not settings.personal_ai_context_identity_mapping_reference
    ):
        raise HTTPException(403, "owner_not_authorized")
    owner = session.scalar(
        select(FirebaseOwnerBinding.owner_id).where(
            FirebaseOwnerBinding.firebase_uid == settings.firebase_owner_uid
        )
    )
    if owner is None or owner != settings.local_owner_id:
        raise HTTPException(503, "owner_binding_unavailable")
    from firebase_admin import auth as firebase_auth

    from shopping.projects.dependencies import _firebase_app

    try:
        linked_user = firebase_auth.get_user(
            settings.firebase_owner_uid, app=_firebase_app(settings.firebase_project_id or "")
        )
    except (firebase_auth.UserNotFoundError, firebase_auth.UserDisabledError) as error:
        raise HTTPException(403, "owner_not_authorized") from error
    except Exception as error:
        raise HTTPException(503, "linked_owner_identity_unavailable") from error
    revoked_after = getattr(linked_user, "tokens_valid_after_timestamp", None)
    linked = any(
        getattr(provider, "provider_id", None) == "google.com"
        and getattr(provider, "uid", None) == identity.subject
        for provider in getattr(linked_user, "provider_data", ())
    )
    if (
        getattr(linked_user, "uid", None) != settings.firebase_owner_uid
        or getattr(linked_user, "disabled", True) is not False
        or not linked
        or type(revoked_after) is not int
        or revoked_after < 0
        or identity.authenticated_at * 1000 < revoked_after
    ):
        raise HTTPException(403, "owner_not_authorized")
    request.state.owner_key = sha256(str(owner).encode()).hexdigest()[:16]
    return owner, request.headers["x-user-delegation"]


class TaskAuthorityUnavailable(RuntimeError):
    pass


class PersonalAITaskAuthority:
    """Recheck exact canonical PAI intent, confirmation and current dependencies.

    The request-bound PAI assertion exists only for this request. The callback has no
    retries; unavailable authority fails before Shopping creates an effect.
    """

    def __init__(
        self,
        settings: Settings,
        user_delegation: str,
        *,
        transport=None,
        service_token_fetcher=None,
    ):
        self.settings = settings
        self.user_delegation = user_delegation
        self.transport = transport
        self.service_token_fetcher = service_token_fetcher or self._service_token

    def _service_token(self):
        google_request = _bounded_google_request_type()()
        try:
            token = id_token.fetch_id_token(
                google_request, self.settings.personal_ai_tasks_authority_audience
            )
        except Exception as error:
            raise TaskAuthorityUnavailable("task_authority_identity_unavailable") from error
        finally:
            google_request.session.close()
        claims = _verify_token(
            token,
            audience=self.settings.personal_ai_tasks_authority_audience,
            identity_unavailable="task_authority_identity_unavailable",
        )
        if claims.get("email") != self.settings.personal_ai_tasks_callback_service_account:
            raise TaskAuthorityUnavailable("task_authority_identity_unavailable")
        return token

    def __call__(self, task: DelegatedTaskRequest, effect: bool) -> bool:
        try:
            token = self.service_token_fetcher()
            with httpx.Client(
                timeout=3.0, follow_redirects=False, trust_env=False, transport=self.transport
            ) as client:
                with client.stream(
                    "POST",
                    self.settings.personal_ai_tasks_authority_base_url.rstrip("/")
                    + "/v1/mutations/task-authority",
                    json={"task": task.model_dump(mode="json"), "effect": effect},
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-User-Delegation": self.user_delegation,
                        "X-Application-ID": "shopping",
                    },
                ) as response:
                    if response.status_code != 200:
                        raise TaskAuthorityUnavailable("task_authority_unavailable")
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 4096:
                            raise TaskAuthorityUnavailable("task_authority_response_invalid")
                    import json

                    result = json.loads(raw)
                    if (
                        not isinstance(result, dict)
                        or set(result) != {"allowed"}
                        or type(result["allowed"]) is not bool
                    ):
                        raise TaskAuthorityUnavailable("task_authority_response_invalid")
                    return result["allowed"]
        except (httpx.HTTPError, ValueError, HTTPException) as error:
            raise TaskAuthorityUnavailable("task_authority_unavailable") from error
