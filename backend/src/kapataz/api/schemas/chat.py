"""Esquemas del chat."""

from pydantic import BaseModel, ConfigDict, Field

from kapataz.application.use_cases.stream_chat_reply import MAX_CHAT_MESSAGE_LENGTH


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=MAX_CHAT_MESSAGE_LENGTH)
