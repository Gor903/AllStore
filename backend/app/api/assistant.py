from fastapi import APIRouter, HTTPException, status

from app.deps.auth import SessionDep, SettingsDep
from app.schemas.assistant import AssistantAnswer, AssistantAskRequest
from app.schemas.catalog import CatalogProductRead
from app.services.assistant import conversation
from app.services.assistant.client import AssistantUnavailableError, build_model

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/ask", response_model=AssistantAnswer)
async def ask(
    payload: AssistantAskRequest, session: SessionDep, settings: SettingsDep
) -> AssistantAnswer:
    """Open to a guest: someone who has bought nothing yet is exactly who this is for.

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
    try:
        answer = await conversation.ask(
            session, settings, build_model(settings), payload.question, history
        )
    except AssistantUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Помощник сейчас не отвечает. Поиск по каталогу работает как обычно.",
        ) from None
    return AssistantAnswer(
        answer=answer.text,
        products=[CatalogProductRead.from_product(product) for product in answer.products],
    )
