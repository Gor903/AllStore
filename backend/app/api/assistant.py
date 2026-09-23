from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.deps.auth import SessionDep, SettingsDep
from app.schemas.assistant import (
    AssistantAskRequest,
    AssistantError,
    AssistantLine,
    AssistantProducts,
    AssistantText,
)
from app.schemas.catalog import CatalogProductRead
from app.services.assistant import conversation
from app.services.assistant.client import AssistantUnavailableError, build_model

router = APIRouter(prefix="/assistant", tags=["assistant"])

UNAVAILABLE = "Помощник сейчас не отвечает. Поиск по каталогу работает как обычно."


@router.post(
    "/ask",
    responses={
        200: {
            "model": AssistantLine,
            "description": (
                "A stream of JSON lines, `application/x-ndjson`: one object per line, in the "
                "order they become ready. The schema describes a single line, not the body."
            ),
        }
    },
)
async def ask(
    payload: AssistantAskRequest, session: SessionDep, settings: SettingsDep
) -> StreamingResponse:
    """Open to a guest: someone who has bought nothing yet is exactly who this is for.

    The reply is a stream of JSON lines, not one object, so the products can reach the visitor
    as soon as the search finds them instead of waiting out the model.

    No CSRF gate, for the same reason complaints have none: the request carries nobody's
    privileges, and forging it from another site achieves what its author could do directly.
    There is no rate limiting in this project at all (see the stage 14 journal), and this
    endpoint costs processor time — so the work is bounded from above instead: by the length
    of the question, the length of the history and the number of search rounds.
    """
    if settings.assistant_base_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Помощник пока не подключён.",
        )
    history = [turn.model_dump() for turn in payload.history[-settings.assistant_history_turns :]]
    return StreamingResponse(
        _lines(session, settings, payload.question, history),
        media_type="application/x-ndjson",
    )


async def _lines(
    session: AsyncSession, settings: Settings, question: str, history: list[dict[str, str]]
) -> AsyncIterator[str]:
    try:
        async for event in conversation.stream(
            session, settings, build_model(settings), question, history
        ):
            if isinstance(event, conversation.Found):
                yield _line(
                    AssistantProducts(
                        products=[
                            CatalogProductRead.from_product(product) for product in event.products
                        ]
                    )
                )
            else:
                yield _line(AssistantText(text=event.text))
    except AssistantUnavailableError:
        # the status code left with the headers, so the honest failure travels as a line
        yield _line(AssistantError(message=UNAVAILABLE))


def _line(event: AssistantLine) -> str:
    return event.model_dump_json() + "\n"
