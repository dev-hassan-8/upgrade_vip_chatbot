import logging

from fastapi import APIRouter, HTTPException

from app.models.chat import ChatRequest, ChatResponse, ConversationHistoryResponse, ConversationMessage
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        service = ChatService()
        return service.chat(message=message, conversation_id=request.conversation_id)
    except RuntimeError as exc:
        logger.exception("Configuration error during chat request")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Chat request failed")
        raise HTTPException(
            status_code=503,
            detail="The assistant is busy at the moment. Please try again in a few seconds.",
        ) from exc
