"""GitHub App installation routes.

`/install/start` and `/install/callback` are browser-facing redirects;
`/installations` and `/installations/{id}/repositories` are JSON endpoints.
Installation IDs from the browser are always re-verified server-side.
"""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse

from app.api.deps import get_current_user, get_github_bundle
from app.core.errors import ApiError
from app.schemas.serializers import installation_view, pagination_view, repository_view

logger = logging.getLogger("flowlens.github_routes")

router = APIRouter(prefix="/api/v1/github", tags=["github"])


def _frontend_redirect(frontend_origin: str, path: str, query: dict[str, str]) -> RedirectResponse:
    separator = "?" if query else ""
    suffix = f"/{path}" if path else ""
    return RedirectResponse(
        url=f"{frontend_origin}{suffix}{separator}{urlencode(query)}",
        status_code=302,
    )


@router.get("/install/start")
def install_start(user=Depends(get_current_user), bundle=Depends(get_github_bundle)):
    """Redirect to the GitHub App installation page with a one-time state."""
    settings = bundle.settings
    if not settings.github_app_slug:
        raise ApiError(
            status_code=503,
            code="GITHUB_APP_NOT_CONFIGURED",
            message="The FlowLens GitHub App is not configured on the server.",
        )
    install_url = bundle.installation_service.install_start(user)
    return RedirectResponse(url=install_url, status_code=302)


@router.get("/install/callback")
def install_callback(
    installation_id: int | None = None,
    setup_action: str | None = None,
    state: str | None = None,
    user=Depends(get_current_user),
    bundle=Depends(get_github_bundle),
):
    """Validate state, verify installation ownership, record, redirect to frontend."""
    settings = bundle.settings
    if installation_id is None or not state:
        return _frontend_redirect(settings.frontend_origin, "", {"install_error": "INSTALLATION_NOT_FOUND"})
    try:
        info = bundle.installation_service.complete_install_callback(
            user, state=state, installation_id=installation_id
        )
    except ValueError:
        logger.info("install callback invalid state", extra={"context": {}})
        return _frontend_redirect(
            settings.frontend_origin, "", {"install_error": "OAUTH_STATE_INVALID"}
        )
    except PermissionError:
        logger.info("install callback denied", extra={"context": {}})
        return _frontend_redirect(
            settings.frontend_origin, "", {"install_error": "REPOSITORY_ACCESS_DENIED"}
        )
    except ApiError as exc:
        return _frontend_redirect(settings.frontend_origin, "", {"install_error": exc.code})
    return _frontend_redirect(
        settings.frontend_origin,
        "projects",
        {"installed_account": info.account_login, "setup_action": setup_action or "installed"},
    )


@router.get("/installations")
def list_installations(user=Depends(get_current_user), bundle=Depends(get_github_bundle)):
    """Installations accessible to the authenticated user (verified live)."""
    installations = bundle.installation_service.list_user_installations(user)
    return {"items": [installation_view(info) for info in installations]}


@router.get("/installations/{installation_id}/repositories")
def list_repositories(
    installation_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    user=Depends(get_current_user),
    bundle=Depends(get_github_bundle),
):
    """Paginated repositories the user and installation are both permitted to access."""
    repositories, _installation = bundle.installation_service.list_repositories(
        user, installation_id, page=page, per_page=per_page
    )
    return {
        "items": [repository_view(repo) for repo in repositories.items],
        "pagination": pagination_view(page, per_page, repositories.total),
    }
