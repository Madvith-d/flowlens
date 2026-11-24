"""CSRF / Origin validation for state-changing cookie-authenticated requests.

Rules:
- For unsafe HTTP methods (POST/PUT/PATCH/DELETE), if the request carries the
  application session cookie, its `Origin` header must match an allowed origin.
- Requests without the session cookie are not treated as CSRF-protected
  browser sessions (non-browser clients), but Origin is still checked when
  present.
- Redirect-target endpoints (GitHub OAuth callbacks) are exempted: they are
  GET requests from github.com.
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("flowlens.csrf")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class OriginValidationMiddleware(BaseHTTPMiddleware):
    """Rejects cross-origin unsafe requests for authenticated sessions."""

    def __init__(self, app, allowed_origins: list[str], session_cookie_name: str) -> None:
        super().__init__(app)
        self.allowed_origins = set(allowed_origins)
        self.session_cookie_name = session_cookie_name

    async def dispatch(self, request: Request, call_next):
        if request.method in UNSAFE_METHODS:
            is_authenticated = self.session_cookie_name in request.cookies
            origin = request.headers.get("origin")
            if is_authenticated or origin is not None:
                if origin not in self.allowed_origins:
                    logger.warning(
                        "csrf origin rejected",
                        extra={"context": {"method": request.method, "origin": origin}},
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": {
                                "code": "CSRF_ORIGIN_REJECTED",
                                "message": "Request origin is not allowed.",
                                "details": {},
                                "request_id": getattr(request.state, "request_id", ""),
                            }
                        },
                    )
        return await call_next(request)
