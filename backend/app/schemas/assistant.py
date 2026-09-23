from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.catalog import CatalogProductRead

QUESTION_MAX_LENGTH = 500
TURN_MAX_LENGTH = 2000


class AssistantTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=TURN_MAX_LENGTH)


class AssistantAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=QUESTION_MAX_LENGTH)
    # the client keeps the conversation and sends it back: the assistant holds no state of its
    # own, so a restart loses nothing and two tabs do not share a thread
    history: list[AssistantTurn] = Field(default_factory=list)


class AssistantAnswer(BaseModel):
    """The text and the products it is allowed to be about.

    Cards are rendered from `products`, never parsed out of `answer`: what the assistant says
    and what the catalogue actually holds must not be able to disagree.
    """

    answer: str
    products: list[CatalogProductRead]
