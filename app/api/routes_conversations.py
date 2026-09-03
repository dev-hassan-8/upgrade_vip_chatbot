import logging

from fastapi import APIRouter, HTTPException

from app.models.chat import ConversationHistoryResponse, ConversationMessage
from app.services.conversation_store import get_conversation_store

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("/{conversation_id}", response_model=ConversationHistoryResponse)
def get_conversation(conversation_id: str) -> ConversationHistoryResponse:
    store = get_conversation_store()
    messages = store.get_messages(conversation_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    return ConversationHistoryResponse(
        conversation_id=conversation_id,
        messages=[ConversationMessage(**message) for message in messages],
    )
