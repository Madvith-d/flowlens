"""Authentication routes.

`/auth/github/start` and `/callback` are browser-facing redirects; `/me` and
`/logout` are JSON endpoints. No response ever contains GitHub tokens.
"""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse, Response

from app.api.deps import get_auth_bundle, get_settings
from app.core.errors import ApiError
from app.services.auth.service import AUTH_REQUIRED

logger = logging.getLogger("flowlens.auth_routes")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _frontend_redirect(settings, query: dict[str, str]) -> RedirectResponse:
    from urllib.parse import urlencode

    separator = "?" if query else ""
    return RedirectResponse(
        url=f"{settings.frontend_origin}/{separator}{urlencode(query)}",
        status_code=302,
    )


@router.get("/github/start")
def github_start(bundle=Depends(get_auth_bundle)):
    """Initiate GitHub App user authorization with a one-time state."""
    settings = bundle.settings
    if not settings.github_app_client_id:
        raise ApiError(
            status_code=503,
            code="GITHUB_APP_NOT_CONFIGURED",
            message="GitHub App OAuth credentials are not configured on the server.",
        )
    authorize_url = bundle.service.start()
    return RedirectResponse(url=authorize_url, status_code=302)


@router.get("/github/callback")
def github_callback(
    code: str | None = None,
    state: str | None = None,
    bundle=Depends(get_auth_bundle),
):
    """Validate state, exchange the code server-side, establish the session."""
    settings = bundle.settings
    if not code or not state:
        return _frontend_redirect(settings, {"login_error": "OAUTH_STATE_INVALID"})
    try:
        user = bundle.service.complete_callback(state=state, code=code)
    except ApiError as exc:
        # Browser-facing flow: redirect with a stable error code, no envelope.
        logger.info("oauth callback failed", extra={"context": {"code": exc.code}})
        return _frontend_redirect(settings, {"login_error": exc.code})
    session = bundle.service.create_session(user)
    response = _frontend_redirect(settings, {})
    response.set_cookie(
        key=settings.session_cookie_name,
        value=bundle.service.session_cookie_value(session),
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/me")
def auth_me(bundle=Depends(get_auth_bundle)):
    """Current session state; never includes GitHub tokens.

    An absent/expired/invalid session is reported with HTTP 200 and
    `authenticated: false` per the SessionState contract, so the frontend can
    treat sign-in state uniformly instead of error-handling it.
    """
    resolved = bundle.resolve_session()
    if resolved is None:
        return {"authenticated": False, "user": None}
    _session, user = resolved
    return {
        "authenticated": True,
        "user": user.public_view(),
    }


@router.post("/logout", status_code=204)
def logout(bundle=Depends(get_auth_bundle)):
    resolved = bundle.resolve_session()
    if resolved is None:
        raise AUTH_REQUIRED
    session, _user = resolved
    bundle.service.logout(session.id)
    settings = bundle.settings
    response = Response(status_code=204)
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        samesite="lax",
        httponly=True,
    )
    return response
