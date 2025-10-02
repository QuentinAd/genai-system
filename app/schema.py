from typing import Annotated
from pydantic import BaseModel, StringConstraints


class ChatInput(BaseModel):
    """Schema for chat requests."""

    message: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1),
    ]
