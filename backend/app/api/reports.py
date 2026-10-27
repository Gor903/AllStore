import enum
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.deps.auth import OptionalUser, SessionDep, require_csrf, require_role
from app.models import User, UserRole
from app.schemas.moderation import ModerationReasonRequest
from app.schemas.report import (
    ReportAccepted,
    ReportedSubjectRead,
    ReportQueueResponse,
    ReportRequest,
    ReportResolutionResponse,
)
from app.services import reports as reports_service

public_router = APIRouter(prefix="/reports", tags=["reports"])
router = APIRouter(prefix="/moderation/reports", tags=["reports"])

ModeratorUser = Annotated[User, Depends(require_role(UserRole.MODERATOR, UserRole.ADMIN))]

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
Offset = Annotated[int, Query(ge=0)]


class Subject(enum.StrEnum):
    PRODUCT = "product"
    BUSINESS = "business"


@public_router.post("", response_model=ReportAccepted, status_code=status.HTTP_201_CREATED)
async def submit_report(
    payload: ReportRequest,
    session: SessionDep,
    reporter: OptionalUser,
) -> ReportAccepted:
    """No CSRF gate here, unlike every other mutation.

    Double submit protects actions that ride on the caller's own credentials; this one
    carries no authority at all — it files a sentence for a moderator to read. Forging it
    from another site achieves nothing an author could not do by posting directly. The
    gate would, however, shut out the guest the complaint exists for: the CSRF cookie is
    only issued with a session.
    """
    if payload.product_id is not None:
        report = await reports_service.report_product(
            session, reporter, payload.product_id, payload.reason
        )
    else:
        assert payload.subdomain is not None  # noqa: S101 — the schema enforces one subject
        report = await reports_service.report_shop(
            session, reporter, payload.subdomain, payload.reason
        )
    await session.commit()
    return ReportAccepted(id=report.id)


@router.get("", response_model=ReportQueueResponse)
async def read_queue(
    _: ModeratorUser,
    session: SessionDep,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> ReportQueueResponse:
    subjects, products, businesses, total = await reports_service.list_queue(session, limit, offset)
    return ReportQueueResponse(
        items=[ReportedSubjectRead.of(item, products, businesses) for item in subjects],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{subject}/{subject_id}/uphold",
    response_model=ReportResolutionResponse,
    dependencies=[Depends(require_csrf)],
)
async def uphold(
    subject: Subject,
    subject_id: uuid.UUID,
    payload: ModerationReasonRequest,
    moderator: ModeratorUser,
    session: SessionDep,
) -> ReportResolutionResponse:
    """The complaint was right. The product comes off the shelf and the shop off the air
    through the moderation that already exists, so the seller reads it in the same history
    as any other verdict."""
    closed = (
        await reports_service.uphold_product(session, moderator, subject_id, payload.reason)
        if subject is Subject.PRODUCT
        else await reports_service.uphold_business(session, moderator, subject_id, payload.reason)
    )
    await session.commit()
    return ReportResolutionResponse(closed=closed)


@router.post(
    "/{subject}/{subject_id}/dismiss",
    response_model=ReportResolutionResponse,
    dependencies=[Depends(require_csrf)],
)
async def dismiss(
    subject: Subject,
    subject_id: uuid.UUID,
    payload: ModerationReasonRequest,
    moderator: ModeratorUser,
    session: SessionDep,
) -> ReportResolutionResponse:
    """Nothing happens to the subject, so the reason is the only record of the decision —
    which is why it is required."""
    closed = (
        await reports_service.dismiss_product(session, moderator, subject_id, payload.reason)
        if subject is Subject.PRODUCT
        else await reports_service.dismiss_business(session, moderator, subject_id, payload.reason)
    )
    await session.commit()
    return ReportResolutionResponse(closed=closed)
