"""The one envelope a refusal travels in, and how different troubles get into it.

The whole API answers in one shape — `{"error": {code, message, details}}` — and the frontend
leans on it: `lib/errors.ts` reads that shape and only that shape. So what is checked here is
not the wording but that the shape is the same for all four sources of refusal: our own error,
a failed validation, an error from the HTTP layer, and something nobody handled.
"""

from typing import Any

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from app.core.errors import (
    AppError,
    BreachedPasswordError,
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    TooManyRequestsError,
    error_payload,
    register_exception_handlers,
)


def _app(raises: Exception) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise raises

    @app.get("/typed/{number}")
    async def typed(number: int) -> dict[str, int]:
        return {"number": number}

    # the exception must not surface in the test client: the answer is what is under test
    return TestClient(app, raise_server_exceptions=False)


def test_the_envelope_has_the_same_three_fields_whatever_happened() -> None:
    payload = error_payload("some_code", "something went wrong")

    assert payload == {
        "error": {"code": "some_code", "message": "something went wrong", "details": []}
    }


@pytest.mark.parametrize(
    ("error", "code", "expected_status"),
    [
        (NotFoundError("no such thing"), "not_found", status.HTTP_404_NOT_FOUND),
        (ConflictError("already there"), "conflict", status.HTTP_409_CONFLICT),
        (
            PayloadTooLargeError("too big"),
            "payload_too_large",
            status.HTTP_413_CONTENT_TOO_LARGE,
        ),
        (AppError("unclear"), "internal_error", status.HTTP_500_INTERNAL_SERVER_ERROR),
    ],
)
def test_a_known_failure_keeps_its_own_code_and_status(
    error: AppError, code: str, expected_status: int
) -> None:
    response = _app(error).get("/boom")

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["message"] == str(error)


def test_details_travel_so_the_form_can_point_at_the_field() -> None:
    """The frontend spreads `details` over the form fields — see `toFormError` in errors.ts."""
    details: list[dict[str, Any]] = [{"loc": ["body", "email"], "msg": "already taken"}]

    response = _app(ConflictError("taken", details)).get("/boom")

    assert response.json()["error"]["details"] == details


def test_a_refusal_by_quota_says_when_to_come_back() -> None:
    """`Retry-After` is how to say "later" so that a client understands it without reading."""
    response = _app(TooManyRequestsError("too often", retry_after=42)).get("/boom")

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.headers["Retry-After"] == "42"


def test_without_a_known_wait_the_header_is_omitted_rather_than_guessed() -> None:
    response = _app(TooManyRequestsError("too often")).get("/boom")

    assert "Retry-After" not in response.headers


def test_a_breached_password_is_a_validation_failure_and_not_a_refusal() -> None:
    """The person has done nothing wrong: they chose something that is no longer a secret, and
    the thing to do about it is choose again. 422 rather than 403 says exactly that."""
    response = _app(BreachedPasswordError("this password has leaked")).get("/boom")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["error"]["code"] == "password_breached"


def test_request_validation_arrives_in_the_same_envelope() -> None:
    """Otherwise the frontend would have to read two shapes: ours and pydantic's."""
    response = _app(NotFoundError("never raised")).get("/typed/not-a-number")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    body = response.json()["error"]
    assert body["code"] == "validation_failed"
    assert body["details"], "the details are what the form highlights a field by"


def test_a_missing_route_is_not_found_rather_than_an_http_error() -> None:
    """A 404 from the router and a 404 from our own code have to read the same."""
    response = _app(NotFoundError("never raised")).get("/no-such-route")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["error"]["code"] == "not_found"


def test_an_unhandled_error_says_nothing_about_itself(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Outwards, exactly "internal_error" and not one line of the traceback: that goes to the
    log the unhandled-errors rule in infra/observability watches."""
    response = _app(ZeroDivisionError("division by zero")).get("/boom")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == error_payload("internal_error", "Internal server error")
    assert "division by zero" not in response.text
    assert "unhandled error on" in caplog.text
