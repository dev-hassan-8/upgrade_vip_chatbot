from app.services.grounding import CONTACT_EMAIL, GroundingService


def test_unconfirmed_airport_is_detected() -> None:
    service = GroundingService()
    assert service.find_unconfirmed_airports("Do you operate at London Gatwick?") == ["London Gatwick"]
    assert service.find_unconfirmed_airports("Manchester Terminal 2 please") == ["Manchester"]
    assert service.find_confirmed_airports("Heathrow meet and greet") == ["Heathrow"]


def test_contact_only_services_detected() -> None:
    service = GroundingService()
    assert service.detect_contact_only_service("Can you book a hotel for me?") == "hotel"
    assert service.detect_contact_only_service("I need a private jet charter") == "private_jet"
    assert service.detect_contact_only_service("Hire a bodyguard in London") == "bodyguard"
    assert service.detect_contact_only_service("Book a helicopter transfer") == "helicopter"
    assert service.detect_contact_only_service("Airport VIP at Heathrow") is None


def test_pricing_fallback_covers_cost_and_discount() -> None:
    service = GroundingService()
    answer = service.ensure_answer_covers_grounding(
        "How much does it cost and do you offer a discount?",
        "We sometimes offer discounts for returning clients.",
    )
    lowered = answer.lower()
    assert "not available" in lowered or "pricing" in lowered
    assert CONTACT_EMAIL in answer
    assert "7414 246103" in answer
    assert "£" not in answer or "not available" in lowered


def test_pricing_invented_amount_is_stripped() -> None:
    service = GroundingService()
    answer = service.ensure_answer_covers_grounding(
        "How much is Airport VIP?",
        "Airport VIP usually costs £450 per passenger.",
    )
    assert "£450" not in answer
    assert CONTACT_EMAIL in answer


def test_hotel_booking_forces_contact_route() -> None:
    service = GroundingService()
    answer = service.ensure_answer_covers_grounding(
        "Please book a hotel near Heathrow",
        "Yes, I can book that hotel for you right now.",
    )
    lowered = answer.lower()
    assert "hotel" in lowered
    assert "airport vip" in lowered or "airport transfers" in lowered
    assert CONTACT_EMAIL in answer
    assert "i can book that hotel" not in lowered


def test_private_jet_forces_contact_route() -> None:
    service = GroundingService()
    answer = service.ensure_answer_covers_grounding(
        "Can you book a private jet?",
        "Sure, I will arrange the private jet charter here.",
    )
    assert CONTACT_EMAIL in answer
    assert "cannot" in answer.lower() or "transfers" in answer.lower()


def test_unconfirmed_airport_false_confirmation_rewritten() -> None:
    service = GroundingService()
    answer = service.ensure_answer_covers_grounding(
        "Do you operate at Gatwick?",
        "Yes, we operate at Gatwick and can meet you there.",
    )
    lowered = answer.lower()
    assert "350+" in lowered or "350 +" in lowered
    assert "does not specifically confirm" in lowered or "not specifically confirm" in lowered
    assert "yes, we operate at gatwick" not in lowered


def test_terminal_invention_rewritten() -> None:
    service = GroundingService()
    answer = service.ensure_answer_covers_grounding(
        "Do you cover Manchester Terminal 2?",
        "Yes, we operate in Terminal 2 at Manchester with our dedicated desk.",
    )
    lowered = answer.lower()
    assert "specifically confirm" in lowered or "350+" in lowered
    assert "dedicated desk" not in lowered


def test_grounding_directives_include_key_rules() -> None:
    service = GroundingService()
    text = service.build_grounding_directives(
        "How much for VIP at Gatwick and can you book a hotel?"
    )
    lowered = text.lower()
    assert "pricing" in lowered
    assert "gatwick" in lowered or "london gatwick" in lowered
    assert "hotel" in lowered
    assert CONTACT_EMAIL in text


def test_boost_retrieval_adds_capability_keywords() -> None:
    service = GroundingService()
    boosted = service.boost_retrieval_query("Book a private jet please")
    assert "bot capabilities" in boosted
    assert "private jet" in boosted.lower()


def test_concierge_employment_hallucination_rewritten() -> None:
    service = GroundingService()
    answer = service.ensure_answer_covers_grounding(
        "Are all 20,000 concierges your employees?",
        "Yes, all 20,000 concierges are UpgradeVIP employees.",
    )
    lowered = answer.lower()
    assert "local operators" in lowered
    assert "does not say that all" in lowered
    assert "are upgradevip employees." not in lowered.replace("does not say that all 20,000 concierges are direct upgradevip employees", "")


def test_lounge_partnership_hallucination_rewritten() -> None:
    service = GroundingService()
    answer = service.ensure_answer_covers_grounding(
        "Do you own the airport lounges or partner with airlines?",
        "Yes we partner with BA lounges and own several suites.",
    )
    lowered = answer.lower()
    assert "does not confirm" in lowered
    assert "ba lounges" not in lowered
    assert "fortune 500" in lowered


def test_guarantee_extra_conditions_rewritten() -> None:
    service = GroundingService()
    answer = service.ensure_answer_covers_grounding(
        "What is the Travel Delight Guarantee?",
        "Our third-party suppliers guarantee refunds under their policies.",
    )
    lowered = answer.lower()
    assert "in-house concierge" in lowered
    assert "service fee" in lowered
    assert "third-party suppliers guarantee" not in lowered
