from __future__ import annotations

import re
from typing import Any

from app.models.booking import (
    AirportTransferEnquiry,
    AirportVipEnquiry,
    EnquiryState,
    EnquiryStatus,
    EnquiryType,
)


class BookingService:
    VIP_START_PATTERNS = (
        "airport vip",
        "vip service",
        "meet and greet",
        "meet & greet",
        "fast track",
        "lounge access",
        "vip airport",
    )
    TRANSFER_START_PATTERNS = (
        "airport transfer",
        "private transfer",
        "chauffeur",
        "pick me up",
        "drop me off",
        "transfer from",
        "transfer to",
        "need a car",
        "book a transfer",
    )

    VIP_FIELDS = (
        ("airport", "Which airport will you be travelling through?"),
        ("service_date", "What date will you be travelling?"),
        ("service_time", "What time will you need the service?"),
        ("passenger_count", "How many passengers will there be?"),
        ("passenger_name", "May I have the lead passenger name?"),
        ("contact_email", "What's the best email to reach you on?"),
        ("contact_phone", "And a contact phone number?"),
    )

    TRANSFER_FIELDS = (
        ("airport", "Which airport will you be travelling through?"),
        ("pickup_location", "Where should we pick you up?"),
        ("dropoff_location", "Where would you like to be dropped off?"),
        ("service_date", "What date will you be travelling?"),
        ("service_time", "What time will you need the transfer?"),
        ("passenger_count", "How many passengers will there be?"),
        ("passenger_name", "May I have the lead passenger name?"),
        ("contact_email", "What's the best email to reach you on?"),
        ("contact_phone", "And a contact phone number?"),
    )

    def detect_intent(self, message: str) -> EnquiryType:
        text = message.lower()
        if any(pattern in text for pattern in self.TRANSFER_START_PATTERNS):
            return EnquiryType.AIRPORT_TRANSFER
        if any(pattern in text for pattern in self.VIP_START_PATTERNS):
            return EnquiryType.AIRPORT_VIP
        if "transfer" in text and "airport" in text:
            return EnquiryType.AIRPORT_TRANSFER
        if "vip" in text and ("book" in text or "arrange" in text or "need" in text):
            return EnquiryType.AIRPORT_VIP
        return EnquiryType.NONE

    def start_enquiry(self, state: EnquiryState, enquiry_type: EnquiryType) -> EnquiryState:
        state.enquiry_type = enquiry_type
        state.status = EnquiryStatus.COLLECTING
        return state

    def update_from_message(self, state: EnquiryState, message: str) -> EnquiryState:
        if state.enquiry_type == EnquiryType.AIRPORT_VIP:
            self._update_model(state.airport_vip, message, self.VIP_FIELDS)
        elif state.enquiry_type == EnquiryType.AIRPORT_TRANSFER:
            self._update_model(state.airport_transfer, message, self.TRANSFER_FIELDS)
        return state

    def next_missing_field(self, state: EnquiryState) -> tuple[str, str] | None:
        for field_name, prompt in self._active_fields(state):
            if not self._field_value(state, field_name):
                return field_name, prompt
        return None

    def mark_complete_if_ready(self, state: EnquiryState) -> EnquiryState:
        if state.enquiry_type != EnquiryType.NONE and self.next_missing_field(state) is None:
            state.status = EnquiryStatus.COMPLETE
        return state

    def build_enquiry_context(self, state: EnquiryState) -> str:
        if state.enquiry_type == EnquiryType.NONE:
            return ""

        if state.enquiry_type == EnquiryType.AIRPORT_VIP:
            enquiry = state.airport_vip.model_dump(exclude_none=True)
            label = "Airport VIP enquiry"
        else:
            enquiry = state.airport_transfer.model_dump(exclude_none=True)
            label = "Airport Transfer enquiry"

        missing = self.next_missing_field(state)
        missing_text = missing[1] if missing else "All key details collected."
        return (
            f"Active {label}.\n"
            f"Collected details: {enquiry}\n"
            f"Next suggested question if needed: {missing_text}\n"
            "Do not confirm a booking. Treat this as an enquiry or booking request."
        )

    def _active_fields(self, state: EnquiryState) -> tuple[tuple[str, str], ...]:
        if state.enquiry_type == EnquiryType.AIRPORT_VIP:
            return self.VIP_FIELDS
        if state.enquiry_type == EnquiryType.AIRPORT_TRANSFER:
            return self.TRANSFER_FIELDS
        return ()

    @staticmethod
    def _field_value(state: EnquiryState, field_name: str) -> Any:
        if state.enquiry_type == EnquiryType.AIRPORT_VIP:
            return getattr(state.airport_vip, field_name)
        if state.enquiry_type == EnquiryType.AIRPORT_TRANSFER:
            return getattr(state.airport_transfer, field_name)
        return None

    def summary_message(self, state: EnquiryState) -> str:
        if state.enquiry_type == EnquiryType.AIRPORT_VIP:
            details = state.airport_vip.model_dump(exclude_none=True)
            service = "Airport VIP"
        elif state.enquiry_type == EnquiryType.AIRPORT_TRANSFER:
            details = state.airport_transfer.model_dump(exclude_none=True)
            service = "Airport Transfer"
        else:
            return ""

        return (
            f"I've got the details for your {service} enquiry. "
            f"Our team can confirm availability and the final price. "
            f"Summary: {details}"
        )

    def _update_model(
        self,
        model: AirportVipEnquiry | AirportTransferEnquiry,
        message: str,
        fields: tuple[tuple[str, str], ...],
    ) -> None:
        text = message.strip()
        if not text:
            return

        for field_name, _ in fields:
            if getattr(model, field_name):
                continue

            value = self._extract_field_value(field_name, text)
            if value is not None:
                setattr(model, field_name, value)
                break

    @staticmethod
    def _extract_field_value(field_name: str, text: str) -> Any:
        lowered = text.lower()

        if field_name == "passenger_count":
            match = re.search(r"\b(\d{1,2})\b", text)
            if match:
                return int(match.group(1))
            if "just me" in lowered or "only me" in lowered:
                return 1

        if field_name in {"contact_email"}:
            match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
            if match:
                return match.group(0)

        if field_name in {"contact_phone"}:
            match = re.search(r"(\+?\d[\d\s\-()]{7,}\d)", text)
            if match:
                return match.group(0).strip()

        if field_name in {"service_date", "service_time", "airport", "passenger_name",
                          "pickup_location", "dropoff_location", "flight_number",
                          "luggage_details", "special_requirements"}:
            if len(text.split()) <= 12:
                return text

        return None
