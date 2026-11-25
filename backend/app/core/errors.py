"""Centralized API error handling with the shared error envelope.

Responses never contain stack traces, secrets, or server filesystem paths.
"""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.middleware import request_id_var

logger = logging.getLogger("flowlens.errors")


class ApiError(Exception):
    """Raise anywhere to produce the standard error envelope."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}

    def to_response(self, request_id: str) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code,
            content={
                "error": {
                    "code": self.code,
                    "message": self.message,
                    "details": self.details,
                    "request_id": request_id,
                }
            },
        )


def _request_id() -> str:
    return request_id_var.get() or uuid.uuid4().hex


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        return exc.to_response(_request_id())

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        return ApiError(
            status_code=400,
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            details={"errors": exc.errors()[:20]},
        ).to_response(_request_id())

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException):
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        return ApiError(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
        ).to_response(_request_id())

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        # Log the real exception internally; never leak it to the client.
        logger.exception("unhandled exception", extra={"context": {"path": request.url.path}})
        request_id = _request_id()
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                    "details": {},
                    "request_id": request_id,
                }
            },
        )
