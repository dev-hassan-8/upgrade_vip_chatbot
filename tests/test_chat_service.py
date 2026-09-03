from unittest.mock import MagicMock, patch

import pytest

from app.models.chat import ChatResponse
from app.services.chat_service import ChatService, strip_code_from_reply


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


def test_strip_code_from_reply_removes_dict_dump() -> None:
    raw = (
        "Thank you. Our team will be in touch.\n\n"
        "I've got the details for your Airport VIP enquiry. "
        "Summary: {'airport': 'Lahore', 'passenger_count': 4, 'extra': {}}"
    )
    cleaned = strip_code_from_reply(raw)
    assert "Summary:" not in cleaned
    assert "{'airport'" not in cleaned
    assert "Our team will be in touch." in cleaned


def test_handover_without_contact_asks_for_details(chat_service: ChatService) -> None:
    chat_service._gemini_client.generate.return_value = (
        "I have successfully passed your enquiry over to our team! "
        "They will be in touch with you shortly."
    )
    with patch.object(chat_service.retrieval_service, "needs_retrieval", return_value=False):
        first = chat_service.chat("I need airport VIP service at Heathrow")
        response = chat_service.chat(
            "Please pass this complete enquiry over to your team",
            conversation_id=first.conversation_id,
        )
    lowered = response.answer.lower()
    assert "successfully passed" not in lowered
    assert "will be in touch" not in lowered
    assert "before i send this over to our team" in lowered
    assert "full name" in lowered
    assert "email" in lowered


def test_false_handover_claim_does_not_spam_contact_cta(chat_service: ChatService) -> None:
    chat_service._gemini_client.generate.return_value = (
        "Heathrow is supported. Our team will be in touch shortly with options."
    )
    with patch.object(chat_service.retrieval_service, "needs_retrieval", return_value=False):
        first = chat_service.chat("I need airport VIP service at Heathrow")
        chat_service._gemini_client.generate.return_value = (
            "Thanks — what date will you travel? Our team will review and be in touch."
        )
        response = chat_service.chat(
            "What date options do I have?",
            conversation_id=first.conversation_id,
        )
    lowered = response.answer.lower()
    assert "before i send this over to our team" not in lowered
    assert "successfully passed" not in lowered
    assert "will be in touch" not in lowered


def test_contact_repeat_complaint_gets_apology(chat_service: ChatService) -> None:
    chat_service._gemini_client.generate.return_value = "Please share your name."
    with patch.object(chat_service.retrieval_service, "needs_retrieval", return_value=False):
        first = chat_service.chat("I need airport VIP service at Heathrow")
        response = chat_service.chat(
            "so why you ask me name again and agin",
            conversation_id=first.conversation_id,
        )
    lowered = response.answer.lower()
    assert "sorry" in lowered or "apologies" in lowered
    assert "before i send this over to our team" not in lowered


def test_retains_heathrow_from_first_message(chat_service: ChatService) -> None:
    chat_service._gemini_client.generate.return_value = "Thanks — what date will you travel?"
    with patch.object(chat_service.retrieval_service, "needs_retrieval", return_value=False):
        response = chat_service.chat(
            "I need airport VIP at Heathrow Airport (LHR) next Monday at 3 PM for 2 passengers"
        )
    store = chat_service.conversation_store
    state = store.get_enquiry_state(response.conversation_id)
    assert state.airport_vip.airport == "Heathrow (LHR)"
    assert state.airport_vip.passenger_count == 2
    assert service_next_is_not_airport(chat_service, state)


def test_complete_enquiry_uses_unified_handover(chat_service: ChatService) -> None:
    chat_service._gemini_client.generate.return_value = (
        "Great, all set. Does this help, or do you have any other questions about your upcoming trip?"
    )
    with patch.object(chat_service.retrieval_service, "needs_retrieval", return_value=False):
        first = chat_service.chat("I need airport VIP at Heathrow")
        cid = first.conversation_id
        for message in (
            "12 June 2026",
            "10:00 am",
            "2",
            "Ali Khan",
            "ali@example.com",
            "+447414246103",
        ):
            response = chat_service.chat(message, conversation_id=cid)
    lowered = response.answer.lower()
    assert "heathrow (lhr)" in lowered
    assert "ali khan" in lowered
    assert lowered.count("does this help") == 0
    assert "- airport:" in lowered


def test_informational_answer_gets_helpful_closing(chat_service: ChatService) -> None:
    chat_service._gemini_client.generate.return_value = (
        "On arrival, your greeter meets you airside.\n\n"
        "Would you like me to add this to your current enquiry?"
    )
    with patch.object(chat_service.retrieval_service, "needs_retrieval", return_value=False):
        response = chat_service.chat("Walk me through the arrival steps")
    lowered = response.answer.lower()
    assert "add this to your current enquiry" not in lowered
    assert "does this help" in lowered


def test_urgent_travel_mentions_whatsapp(chat_service: ChatService) -> None:
    chat_service._gemini_client.generate.return_value = "We can look into VIP support for you."
    with patch.object(chat_service.retrieval_service, "needs_retrieval", return_value=False):
        response = chat_service.chat("My flight lands in 4 hours — need VIP meet and greet")
    assert "+44 7414 246103" in response.answer
    assert "last-minute" in response.answer.lower() or "real-time" in response.answer.lower()


def service_next_is_not_airport(chat_service: ChatService, state) -> bool:
    missing = chat_service.booking_service.next_missing_field(state)
    return missing is not None and missing[0] != "airport"

