from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base for expected, user-facing failures — rendered in the unified error envelope."""

    code = "internal_error"
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str, details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or []

    @property
    def headers(self) -> dict[str, str]:
        """What this refusal needs to say outside the body. Empty for almost every failure —
        the envelope carries the meaning; a header is for what the protocol defines."""
        return {}


class NotFoundError(AppError):
    code = "not_found"
    status_code = status.HTTP_404_NOT_FOUND


class AuthenticationError(AppError):
    code = "authentication_failed"
    status_code = status.HTTP_401_UNAUTHORIZED


class PermissionDeniedError(AppError):
    code = "permission_denied"
    status_code = status.HTTP_403_FORBIDDEN


class PasswordChangeRequiredError(PermissionDeniedError):
    """Signed in, allowed in principle, and not going any further until the password is theirs.

    A distinct code rather than a bare 403: the client has something to do about this one, and
    the thing to do is a screen, not a plea to an administrator.
    """

    code = "password_change_required"


class AccountNotActiveError(PermissionDeniedError):
    """Signed in with something perfectly valid, by an account that may not act.

    Lives here rather than beside either of the services that raise it: `services/auth.py`
    answers it at sign-in and `services/sessions.py` answers it to a session that was revoked
    when the account was barred, and the person must be told the same thing either way.
    """

    code = "account_not_active"


class VerificationRequiredError(PermissionDeniedError):
    """Signed in long enough ago that the platform wants the password again.

    A distinct code because, like `password_change_required`, the client has something to do
    about it: show a box asking for the password, not an apology. The actions behind it are
    the ones nobody should be able to take by sitting down at an unattended screen.
    """

    code = "verification_required"


class EmailNotVerifiedError(PermissionDeniedError):
    """Signed in, allowed in principle, and not opening a shop until the address answers.

    The gate is deliberately narrow — see deps/auth.require_verified_email. A distinct code
    because the client has something to do about it, and the thing to do is to ask for the
    letter again.
    """

    code = "email_not_verified"


class ConflictError(AppError):
    code = "conflict"
    status_code = status.HTTP_409_CONFLICT


class ValidationFailedError(AppError):
    code = "validation_failed"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT


class TooManyRequestsError(AppError):
    code = "too_many_requests"
    status_code = status.HTTP_429_TOO_MANY_REQUESTS

    def __init__(
        self,
        message: str,
        details: list[dict[str, Any]] | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message, details)
        self.retry_after = retry_after

    @property
    def headers(self) -> dict[str, str]:
        """`Retry-After` is how a refusal says when to come back in a way a client can act on
        without reading Russian. Omitted rather than guessed when nobody said."""
        return {} if self.retry_after is None else {"Retry-After": str(self.retry_after)}


class PayloadTooLargeError(AppError):
    code = "payload_too_large"
    status_code = status.HTTP_413_CONTENT_TOO_LARGE


def error_payload(
    code: str, message: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or []}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, exc.details),
            headers=exc.headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details: list[dict[str, Any]] = jsonable_encoder(exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_payload("validation_failed", "Request validation failed", details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == status.HTTP_404_NOT_FOUND else "http_error"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(code, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload("internal_error", "Internal server error"),
        )
