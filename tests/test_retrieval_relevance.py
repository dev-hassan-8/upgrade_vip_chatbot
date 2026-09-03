from app.config import get_settings
from app.services.retrieval_service import RetrievalService, UNAVAILABLE_ANSWER
from app.vectorstore.memory_store import KnowledgeMemoryStore


def _sections(chunks) -> list[str]:
    return [str(chunk.metadata.get("section", "")).lower() for chunk in chunks]


def test_wheelchair_does_not_retrieve_travel_delight() -> None:
    service = RetrievalService(settings=get_settings(), vector_store=KnowledgeMemoryStore(get_settings()))
    query = "Do you provide wheelchair assistance for elderly passengers?"
    chunks = service.retrieve(query)
    assert chunks
    sections = _sections(chunks)
    assert not any("terms & conditions" in section for section in sections)
    assert not any("mission & guarantee" in section for section in sections)
    assert any("service" in section or "who uses" in section for section in sections)


def test_guarantee_wheelchair_avoids_cross_topic_terms() -> None:
    service = RetrievalService(settings=get_settings(), vector_store=KnowledgeMemoryStore(get_settings()))
    query = "Can you guarantee wheelchair assistance at every airport?"
    assert "travel_delight_guarantee" not in service.detect_intents(query)
    chunks = service.retrieve(query)
    sections = _sections(chunks)
    assert not any("terms & conditions" in section for section in sections)


def test_jfk_terminal_retrieves_coverage_not_guarantee() -> None:
    service = RetrievalService(settings=get_settings(), vector_store=KnowledgeMemoryStore(get_settings()))
    chunks = service.retrieve("Do you offer VIP services at JFK Terminal 4?")
    assert chunks
    sections = _sections(chunks)
    assert any("global availability" in section or "featured" in section for section in sections)
    assert not any("terms & conditions" in section for section in sections)


def test_travel_delight_retrieves_terms() -> None:
    service = RetrievalService(settings=get_settings(), vector_store=KnowledgeMemoryStore(get_settings()))
    chunks = service.retrieve("What is the Travel Delight Guarantee?")
    assert chunks
    sections = _sections(chunks)
    assert any("terms & conditions" in section or "mission & guarantee" in section for section in sections)


def test_private_jet_and_hotel_retrieve_bot_capabilities() -> None:
    service = RetrievalService(settings=get_settings(), vector_store=KnowledgeMemoryStore(get_settings()))
    jet = service.retrieve("Can I book a private jet?")
    hotel = service.retrieve("Can you book a hotel?")
    assert any("bot capabilities" in section or "services" in section for section in _sections(jet))
    assert any("bot capabilities" in section or "services" in section for section in _sections(hotel))


def test_pricing_does_not_prefer_coverage_lists() -> None:
    service = RetrievalService(settings=get_settings(), vector_store=KnowledgeMemoryStore(get_settings()))
    chunks = service.retrieve("How much does an Airport VIP Service cost?")
    sections = _sections(chunks)
    assert not any("global availability" in section for section in sections)
    assert chunks  # still returns something useful (services / contact / capabilities)


def test_fast_track_retrieves_vip_services() -> None:
    service = RetrievalService(settings=get_settings(), vector_store=KnowledgeMemoryStore(get_settings()))
    chunks = service.retrieve("Do you offer fast-track security at every airport?")
    assert chunks
    sections = _sections(chunks)
    assert any("service" in section or "global availability" in section for section in sections)
    assert not any("terms & conditions" in section for section in sections)


def test_unavailable_constant() -> None:
    assert "don't have specific information" in UNAVAILABLE_ANSWER.lower()
