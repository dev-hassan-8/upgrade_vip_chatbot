from unittest.mock import MagicMock, patch

import pytest

from app.models.chat import ChatResponse
from app.services.chat_service import ChatService


@pytest.fixture
def chat_service() -> ChatService:
    mock_gemini = MagicMock()
    mock_gemini.generate.return_value = "Hello! How can I help?"
    service = ChatService(ai_client=mock_gemini)
    return service


def test_greeting_does_not_require_sources(chat_service: ChatService) -> None:
    with patch.object(chat_service.retrieval_service, "needs_retrieval", return_value=False):
        response = chat_service.chat("Hi")
        assert isinstance(response, ChatResponse)
        assert response.answer
        assert response.sources == []


def test_knowledge_question_uses_retrieval(chat_service: ChatService) -> None:
    with patch.object(
        chat_service.rag_service,
        "retrieve_context",
        return_value=("UpgradeVIP provides Airport VIP Services and Airport Transfers.", []),
    ), patch.object(chat_service.retrieval_service, "needs_retrieval", return_value=True):
        response = chat_service.chat("What services does UpgradeVIP offer?")
        assert response.answer
