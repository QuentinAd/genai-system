from typing import Annotated, Any
from pydantic import BaseModel, StringConstraints


class ChatInput(BaseModel):
    """Schema for chat requests."""

    message: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1),
    ]
    history: list[dict[str, Any] | list[Any] | str] | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message": "Summarise the latest updates",
                    "history": [
                        {"role": "user", "content": "Hi"},
                        {"role": "assistant", "content": "Hello"},
                    ],
                }
            ]
        }
    }
