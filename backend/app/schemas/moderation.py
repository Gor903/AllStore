from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

REASON_MAX_LENGTH = 1000

# trimmed first, so a line of spaces is not a reason
RejectionReason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REASON_MAX_LENGTH)
]


class ProductRejectRequest(BaseModel):
    """A refusal the seller cannot act on is not a refusal, so the reason is required."""

    model_config = ConfigDict(extra="forbid")

    reason: RejectionReason
