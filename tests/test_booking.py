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
    assert state.airport_transfer.airport == "Heathrow"

    missing = service.next_missing_field(state)
    assert missing is not None
    assert missing[0] == "pickup_location"
