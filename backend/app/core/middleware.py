"""Middleware: request IDs and structured request logging."""

import logging
import time
import uuid
import contextvars

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default=None)  # type: ignore[arg-type]

logger = logging.getLogger("flowlens.request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request ID, logs each request, and returns it in a header."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = uuid.uuid4().hex
        token = request_id_var.set(request_id)
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        # Browsers must not MIME-sniff API responses (reports download as
        # text/markdown, JSON everywhere else).
        response.headers["X-Content-Type-Options"] = "nosniff"
        logger.info(
            "request",
            extra={
                "context": {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                }
            },
        )
        return response
