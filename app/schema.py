from pydantic import BaseModel, constr


class ChatInput(BaseModel):
    """Schema for chat requests."""

    message: constr(min_length=1, strip_whitespace=True)
