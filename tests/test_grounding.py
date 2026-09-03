from app.services.retrieval_service import RetrievalService


def test_conversational_messages_skip_rag() -> None:
    service = RetrievalService.__new__(RetrievalService)
    assert service.needs_retrieval("Hi") is False
    assert service.needs_retrieval("Thanks") is False
    assert service.needs_retrieval("Goodbye") is False


def test_factual_messages_use_rag() -> None:
    service = RetrievalService.__new__(RetrievalService)
    assert service.needs_retrieval("What services does UpgradeVIP offer?") is True
    assert service.needs_retrieval("Do you provide airport transfers?") is True
    assert service.needs_retrieval("Do you operate at Gatwick Terminal 2?") is True
    assert service.needs_retrieval("How much does VIP cost?") is True
    assert service.needs_retrieval("Can you book a private jet?") is True
