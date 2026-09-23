from typing import Annotated, Literal

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


# The answer arrives as a sequence of lines rather than one object, because its two halves are
# ready at very different times. Cards are rendered from `products`, never parsed out of the
# text: what the assistant says and what the catalogue holds must not be able to disagree.


class AssistantProducts(BaseModel):
    type: Literal["products"] = "products"
    products: list[CatalogProductRead]


class AssistantText(BaseModel):
    type: Literal["answer"] = "answer"
    text: str


class AssistantError(BaseModel):
    """A failure that arrives mid-stream, when the status code has long been sent."""

    type: Literal["error"] = "error"
    message: str


# Declared to the schema so the frontend reads these shapes from the contract instead of keeping
# its own copy of them (ADR 4). What the schema cannot say is that they arrive one per line —
# that lives in the response description.
AssistantLine = Annotated[
    AssistantProducts | AssistantText | AssistantError, Field(discriminator="type")
]
