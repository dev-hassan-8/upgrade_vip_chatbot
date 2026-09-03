from app.models.booking import EnquiryState, EnquiryType
from app.services.booking_service import BookingService


def test_detect_airport_transfer_intent() -> None:
    service = BookingService()
    assert service.detect_intent("Can I book an airport transfer from Heathrow?") == EnquiryType.AIRPORT_TRANSFER


def test_detect_airport_vip_intent() -> None:
    service = BookingService()
    assert service.detect_intent("I need airport VIP service at Heathrow") == EnquiryType.AIRPORT_VIP


def test_progressive_field_collection() -> None:
    service = BookingService()
    state = EnquiryState()
    state = service.start_enquiry(state, EnquiryType.AIRPORT_TRANSFER)
    state = service.update_from_message(state, "Heathrow")
    assert state.airport_transfer.airport == "Heathrow (LHR)"

    missing = service.next_missing_field(state)
    assert missing is not None
    assert missing[0] == "pickup_location"


def test_extracts_airport_from_intent_message() -> None:
    service = BookingService()
    state = EnquiryState()
    state = service.start_enquiry(state, EnquiryType.AIRPORT_VIP)
    state = service.update_from_message(
        state,
        "I need airport VIP service at Heathrow Airport (LHR) for 2 passengers next Monday at 3 PM",
    )
    assert state.airport_vip.airport == "Heathrow (LHR)"
    assert state.airport_vip.passenger_count == 2
    assert state.airport_vip.service_date is not None
    assert "monday" in state.airport_vip.service_date.lower()
    assert state.airport_vip.service_time is not None
    missing = service.next_missing_field(state)
    assert missing is not None
    assert missing[0] == "passenger_name"


def test_does_not_reask_airport_when_already_known() -> None:
    service = BookingService()
    state = EnquiryState()
    state = service.start_enquiry(state, EnquiryType.AIRPORT_VIP)
    state = service.update_from_message(state, "VIP meet and greet at Heathrow")
    assert state.airport_vip.airport == "Heathrow (LHR)"
    assert service.next_missing_field(state)[0] != "airport"


def test_rejects_relational_name_fragments() -> None:
    service = BookingService()
    state = EnquiryState()
    state = service.start_enquiry(state, EnquiryType.AIRPORT_VIP)
    state = service.update_from_message(state, "traveling with my wife")
    assert state.airport_vip.passenger_name is None
    state = service.update_from_message(state, "My name is Ali Khan")
    assert state.airport_vip.passenger_name == "Ali Khan"


def test_rejects_garbage_airport_placeholders() -> None:
    service = BookingService()
    assert service._extract_airport("sp") is None
    assert service._extract_airport("at sp") is None
    assert service._extract_airport("DXB") == "Dubai (DXB)"


def test_summary_message_is_human_readable() -> None:
    service = BookingService()
    state = EnquiryState()
    state = service.start_enquiry(state, EnquiryType.AIRPORT_VIP)
    state.airport_vip.airport = "Lahore (LHE)"
    state.airport_vip.passenger_count = 4
    state.airport_vip.contact_email = "freh@gmail.com"
    summary = service.summary_message(state)
    assert "{'" not in summary
    assert "Summary:" not in summary
    assert "- Airport: Lahore (LHE)" in summary
    assert "- Passengers: 4" in summary
    assert "- Email: freh@gmail.com" in summary


def test_strip_redundant_closings_keeps_one() -> None:
    service = BookingService()
    closing = service.informational_closing()
    doubled = f"Here are the car types.\n\n{closing}\n\n{closing}"
    cleaned = service.strip_redundant_closings(doubled)
    assert cleaned.lower().count(closing.lower()) == 1
    with_summary = (
        "Thank you.\n\n- Airport: Heathrow (LHR)\n- Email: a@b.com\n\n"
        f"{closing}"
    )
    cleaned_summary = service.strip_redundant_closings(with_summary)
    assert closing.lower() not in cleaned_summary.lower()
    assert "- Airport: Heathrow (LHR)" in cleaned_summary


def test_has_team_contact_requires_name_and_email_or_phone() -> None:
    service = BookingService()
    state = EnquiryState()
    state = service.start_enquiry(state, EnquiryType.AIRPORT_VIP)
    assert service.has_team_contact(state) is False

    state.airport_vip.passenger_name = "Test User"
    assert service.has_team_contact(state) is False

    state.airport_vip.contact_email = "freh@gmail.com"
    assert service.has_team_contact(state) is True


def test_handover_phrase_detected() -> None:
    service = BookingService()
    assert service.wants_team_handover("Please pass this complete enquiry over to your team")
    assert service.wants_team_handover("Please submit an enquiry")
    assert service.claims_team_handover("I have successfully passed your enquiry over to our team!")


def test_contact_needed_message_asks_for_name_and_email() -> None:
    service = BookingService()
    state = EnquiryState()
    state = service.start_enquiry(state, EnquiryType.AIRPORT_VIP)
    message = service.contact_needed_message(state)
    assert "Before I send this over to our team" in message
    assert "full name" in message
    assert "email" in message


def test_detect_urgent_travel() -> None:
    service = BookingService()
    assert service.detect_urgent_travel("My flight lands in 4 hours")
    assert service.detect_urgent_travel("Need VIP ASAP tonight")
    assert not service.detect_urgent_travel("Travelling next month on 10 May")


def test_informational_question_strips_enquiry_upsell() -> None:
    service = BookingService()
    assert service.is_informational_question("Walk me through the arrival steps")
    assert service.is_informational_question("What cars do you use?")
    assert not service.looks_like_booking_change("What cars do you use?")
    cleaned = service.strip_enquiry_upsell(
        "We use executive saloons and MPVs.\n\nWould you like me to add this to your current enquiry?"
    )
    assert "add this to your current enquiry" not in cleaned.lower()
    assert "executive saloons" in cleaned


def test_invalid_contact_does_not_count_as_lead() -> None:
    service = BookingService()
    state = EnquiryState()
    state = service.start_enquiry(state, EnquiryType.AIRPORT_VIP)
    state.airport_vip.passenger_name = "A"
    state.airport_vip.contact_email = "not-an-email"
    assert service.has_team_contact(state) is False
    state.airport_vip.passenger_name = "Sara Khan"
    state.airport_vip.contact_email = "sara@example.com"
    assert service.has_team_contact(state) is True
