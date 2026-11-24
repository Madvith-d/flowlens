"""FlowLens backend application factory.

Wiring order: logging → settings/engine → middleware (request IDs, CSRF/origin,
CORS) → exception handlers → routers → app state (providers for DI).
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.api.v1.auth import router as auth_router
from app.core.csrf import OriginValidationMiddleware
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestContextMiddleware
from app.services.github.client import HttpxGitHubOAuthProvider

logger = logging.getLogger("flowlens.main")


def create_app(
    settings=None,
    session_factory: sessionmaker | None = None,
    github_provider=None,
) -> FastAPI:
    from app.core.config import Settings, cached_settings

    if settings is None:
        settings = cached_settings()
    if session_factory is None:
        from app.db.session import build_engine, build_session_factory

        engine = build_engine(settings)
        session_factory = build_session_factory(engine)
    else:
        engine = None
    if github_provider is None:
        github_provider = HttpxGitHubOAuthProvider(settings)

    setup_logging()

    app = FastAPI(
        title="FlowLens API",
        version="0.1.0",
        description="Code dependency and change impact visualizer — backend API.",
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.github_provider = github_provider
    app.state.engine = engine

    # Middleware order matters: request IDs must wrap everything; origin checks
    # and CORS wrap the router.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        OriginValidationMiddleware,
        allowed_origins=settings.allowed_origins,
        session_cookie_name=settings.session_cookie_name,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    register_exception_handlers(app)
    app.include_router(auth_router)

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/ready")
    def ready() -> dict[str, str]:
        session = app.state.session_factory()
        try:
            session.execute(text("SELECT 1"))
        except Exception:
            logger.exception("readiness database check failed")
            return {"status": "not-ready"}
        finally:
            session.close()
        return {"status": "ready"}

    return app


app = create_app()
