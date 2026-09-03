from typing import Any

from pydantic import BaseModel, Field


class Source(BaseModel):
    source: str
    section: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str
    sources: list[Source] = Field(default_factory=list)


class ConversationMessage(BaseModel):
    role: str
    content: str


class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    messages: list[ConversationMessage]
