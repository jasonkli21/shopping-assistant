import json
from contextlib import AbstractContextManager
from io import StringIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request

from shopping.main import app
from shopping.projects import dependencies


def _request(authorization="Bearer signed-token"):
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/projects",
            "raw_path": b"/projects",
            "query_string": b"",
            "headers": [(b"authorization", authorization.encode())],
            "client": ("127.0.0.1", 1234),
            "server": ("test", 443),
        }
    )


class _BindingSession(AbstractContextManager):
    def __init__(self, owner_id):
        self.owner_id = owner_id
        self.closed = False

    def scalar(self, _statement):
        return self.owner_id

    def __exit__(self, *_args):
        self.closed = True
        return False


def _firebase_settings():
    return SimpleNamespace(
        auth_mode="firebase",
        firebase_project_id="project-id",
        firebase_owner_uid="owner-uid",
        local_owner_id=uuid4(),
    )


def test_firebase_binding_lookup_uses_a_closed_short_lived_session(monkeypatch):
    from firebase_admin import auth

    settings = _firebase_settings()
    session = _BindingSession(settings.local_owner_id)
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    monkeypatch.setattr(dependencies, "_firebase_app", lambda _project: object())
    monkeypatch.setattr(auth, "verify_id_token", lambda *_args, **_kwargs: {"uid": "owner-uid"})
    monkeypatch.setattr(dependencies, "SessionLocal", lambda: session)

    request = _request()
    assert dependencies.get_owner_id(request) == settings.local_owner_id
    assert session.closed is True
    assert request.state.owner_key


def test_firebase_auth_rejects_missing_tokens_and_unallowlisted_uids(monkeypatch):
    from firebase_admin import auth

    settings = _firebase_settings()
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    monkeypatch.setattr(dependencies, "_firebase_app", lambda _project: object())

    with pytest.raises(HTTPException) as missing:
        dependencies.get_owner_id(_request(""))
    assert missing.value.status_code == 401

    monkeypatch.setattr(auth, "verify_id_token", lambda *_args, **_kwargs: {"uid": "other"})
    with pytest.raises(HTTPException) as forbidden:
        dependencies.get_owner_id(_request())
    assert forbidden.value.status_code == 403
    assert forbidden.value.detail["code"] == "owner_not_authorized"


@pytest.mark.parametrize(
    ("exception", "status_code", "error_code"),
    [
        ("revoked", 401, "invalid_token"),
        ("infra", 503, "token_verification_unavailable"),
    ],
)
def test_firebase_auth_errors_distinguish_invalid_tokens_from_outages(
    monkeypatch, exception, status_code, error_code
):
    from firebase_admin import auth

    settings = _firebase_settings()

    def fail_verification(*_args, **_kwargs):
        if exception == "revoked":
            raise auth.RevokedIdTokenError("token revoked")
        raise auth.CertificateFetchError("certificate fetch failed", RuntimeError("network"))

    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    monkeypatch.setattr(dependencies, "_firebase_app", lambda _project: object())
    monkeypatch.setattr(auth, "verify_id_token", fail_verification)

    with pytest.raises(HTTPException) as raised:
        dependencies.get_owner_id(_request())
    assert raised.value.status_code == status_code
    assert raised.value.detail["code"] == error_code
    assert "token revoked" not in str(raised.value.detail)


def _dependency_calls(dependant):
    calls = {dependant.call}
    for dependency in dependant.dependencies:
        calls.update(_dependency_calls(dependency))
    return calls


def _api_routes(router):
    for route in getattr(router, "routes", ()):
        if isinstance(route, APIRoute):
            yield route
        elif getattr(route, "original_router", None) is not None:
            yield from _api_routes(route.original_router)


def test_every_private_api_route_has_the_owner_dependency():
    private_routes = [
        route
        for route in _api_routes(app)
        if route.path not in {"/health", "/ready"} and not route.path.startswith("/openapi")
    ]
    assert private_routes
    assert all(
        dependencies.get_owner_id in _dependency_calls(route.dependant) for route in private_routes
    )


def test_request_logs_are_enabled_and_exclude_credentials(monkeypatch):
    from fastapi.testclient import TestClient

    from shopping import main

    output = StringIO()
    handler = main.logging.StreamHandler(output)
    main.logger.addHandler(handler)
    try:
        response = TestClient(app).get(
            "/health", headers={"Authorization": "Bearer do-not-log-this"}
        )
    finally:
        main.logger.removeHandler(handler)

    assert response.status_code == 200
    event = json.loads(output.getvalue().strip().splitlines()[-1])
    assert event["event"] == "http_request_headers"
    assert event["request_id"]
    assert "Bearer" not in output.getvalue()
    assert "do-not-log-this" not in output.getvalue()
