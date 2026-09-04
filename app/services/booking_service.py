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

AIRPORT_ALIASES: dict[str, str] = {
    "heathrow": "Heathrow (LHR)",
    "london heathrow": "Heathrow (LHR)",
    "lhr": "Heathrow (LHR)",
    "gatwick": "Gatwick (LGW)",
    "lgw": "Gatwick (LGW)",
    "stansted": "Stansted (STN)",
    "stn": "Stansted (STN)",
    "luton": "Luton (LTN)",
    "ltn": "Luton (LTN)",
    "city airport": "London City (LCY)",
    "london city": "London City (LCY)",
    "lcy": "London City (LCY)",
    "manchester": "Manchester (MAN)",
    "man": "Manchester (MAN)",
    "birmingham": "Birmingham (BHX)",
    "bhx": "Birmingham (BHX)",
    "edinburgh": "Edinburgh (EDI)",
    "edi": "Edinburgh (EDI)",
    "glasgow": "Glasgow (GLA)",
    "gla": "Glasgow (GLA)",
    "dublin": "Dublin (DUB)",
    "dub": "Dublin (DUB)",
    "charles de gaulle": "Paris Charles de Gaulle (CDG)",
    "cdg": "Paris Charles de Gaulle (CDG)",
    "orly": "Paris Orly (ORY)",
    "ory": "Paris Orly (ORY)",
    "schiphol": "Amsterdam Schiphol (AMS)",
    "ams": "Amsterdam Schiphol (AMS)",
    "dubai": "Dubai (DXB)",
    "dxb": "Dubai (DXB)",
    "lahore": "Lahore (LHE)",
    "lhe": "Lahore (LHE)",
    "islamabad": "Islamabad (ISB)",
    "isb": "Islamabad (ISB)",
    "karachi": "Karachi (KHI)",
    "khi": "Karachi (KHI)",
    "jfk": "New York JFK (JFK)",
    "new york jfk": "New York JFK (JFK)",
    "lax": "Los Angeles (LAX)",
    "los angeles": "Los Angeles (LAX)",
}

NAME_REJECT_PHRASES = (
    "traveling with",
    "travelling with",
    "me and my",
    "myself",
    "with my",
    "and my",
    "my wife",
    "my husband",
    "my family",
    "just me",
    "only me",
    "lead passenger",
    "passenger name",
)

NAME_STOPWORDS = {
    "traveling",
    "travelling",
    "with",
    "my",
    "me",
    "myself",
    "and",
    "the",
    "a",
    "an",
    "airport",
    "vip",
    "transfer",
    "service",
    "please",
    "hello",
    "hi",
    "sp",
    "ok",
    "okay",
    "yes",
    "no",
    "thanks",
    "thank",
    "you",
    "name",
    "is",
    "i",
    "am",
    "im",
}

INTENT_NOISE = (
    "i need",
    "i want",
    "please",
    "book",
    "arrange",
    "airport vip",
    "vip service",
    "airport transfer",
    "pass this",
    "submit",
    "enquiry",
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
        "vip terminal",
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
        "luxury car",
        "car transfer",
    )

    VIP_FIELDS = (
        ("airport", "Which airport will you be travelling through?"),
        ("service_date", "What date will you be travelling?"),
        ("service_time", "What time will you need the service?"),
        ("flight_number", "What is the flight number?"),
        ("passenger_count", "How many passengers will there be?"),
        ("luggage_details", "How many bags or pieces of luggage will you have?"),
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
        ("flight_number", "What is the flight number, if you have it?"),
        ("passenger_count", "How many passengers will there be?"),
        ("luggage_details", "How many bags or pieces of luggage will you have?"),
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
        if (
            state.enquiry_type != EnquiryType.NONE
            and self.next_missing_field(state) is None
            and self.has_team_contact(state)
        ):
            state.status = EnquiryStatus.COMPLETE
        return state

    def has_team_contact(self, state: EnquiryState) -> bool:
        if state.enquiry_type == EnquiryType.NONE:
            return False
        name = self._field_value(state, "passenger_name")
        email = self._field_value(state, "contact_email")
        phone = self._field_value(state, "contact_phone")
        if not self._is_valid_name(name):
            return False
        if email and self._is_valid_email(str(email)):
            return True
        if phone and self._is_valid_phone(str(phone)):
            return True
        return False

    @staticmethod
    def _is_valid_name(name: Any) -> bool:
        if not name or not isinstance(name, str):
            return False
        cleaned = name.strip()
        if len(cleaned) < 2:
            return False
        if "@" in cleaned or re.search(r"\d{5,}", cleaned):
            return False
        lowered = cleaned.lower()
        if any(phrase in lowered for phrase in NAME_REJECT_PHRASES):
            return False
        tokens = re.findall(r"[A-Za-z\u0600-\u06FF']+", cleaned)
        if not tokens:
            return False
        if any(token.lower() in NAME_STOPWORDS for token in tokens):
            return False
        # Reject single very short garbage like "sp".
        if len(tokens) == 1 and len(tokens[0]) <= 2:
            return False
        return bool(re.search(r"[A-Za-z\u0600-\u06FF]", cleaned))

    def _extract_airport(self, text: str) -> str | None:
        lowered = text.lower()
        for alias in sorted(AIRPORT_ALIASES.keys(), key=len, reverse=True):
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, lowered):
                return AIRPORT_ALIASES[alias]

        # Do not invent short/typo placeholders from loose "at X" matches.
        match = re.search(
            r"(?:at|from|through|via|arrive(?:s|ing)?\s+at|depart(?:s|ing)?\s+from)\s+"
            r"([A-Za-z][A-Za-z]*(?:\s+[A-Za-z][A-Za-z]*){0,3}(?:\s+airport)?)",
            text,
            re.I,
        )
        if match:
            candidate = match.group(1).strip(" .,")
            candidate_key = candidate.lower().replace(" airport", "").strip()
            if candidate_key in AIRPORT_ALIASES:
                return AIRPORT_ALIASES[candidate_key]
            if (
                candidate
                and len(candidate) >= 8
                and "airport" in candidate.lower()
                and candidate_key not in NAME_STOPWORDS
                and not self._looks_like_intent_only(candidate.lower())
            ):
                return candidate.title()

        stripped = text.strip()
        if re.fullmatch(r"[A-Za-z][A-Za-z\s]{2,30}", stripped):
            key = stripped.lower().replace(" airport", "").strip()
            if key in AIRPORT_ALIASES:
                return AIRPORT_ALIASES[key]
            if "airport" in stripped.lower() and len(stripped) >= 8:
                return stripped.title()

        return None

    @staticmethod
    def _extract_name(text: str) -> str | None:
        lowered = text.lower().strip()
        if BookingService._looks_like_intent_only(lowered):
            return None
        if any(phrase in lowered for phrase in NAME_REJECT_PHRASES):
            return None
        if "@" in text or re.search(r"\+?\d[\d\s\-()]{7,}\d", text):
            return None

        match = re.search(
            r"(?:my name is|i am|i'm|this is|lead passenger(?:\s+is)?)\s+"
            r"([A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*){0,3})",
            text,
            re.I,
        )
        if match:
            candidate = match.group(1).strip(" .,")
            return candidate if BookingService._is_valid_name(candidate) else None

        # Short name-only answers (e.g. "Ali Khan").
        if re.fullmatch(r"[A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+){0,3}", text.strip()):
            candidate = text.strip()
            if BookingService._is_valid_name(candidate):
                return candidate
        return None

    def strip_redundant_closings(self, answer: str) -> str:
        if not answer:
            return answer
        cleaned = answer.strip()
        closing = self.informational_closing()
        # Keep at most one informational closing.
        while cleaned.lower().count(closing.lower()) > 1:
            index = cleaned.lower().rfind(closing.lower())
            cleaned = (cleaned[:index] + cleaned[index + len(closing) :]).strip()
        # If a structured summary block is present, drop the soft closing.
        if re.search(r"(?m)^-\s+(Airport|Lead passenger|Email|Phone):", cleaned):
            cleaned = re.sub(
                rf"(?:\n+)?{re.escape(closing)}\s*$",
                "",
                cleaned,
                flags=re.I,
            ).strip()
        return cleaned

    def unified_handover_message(self, state: EnquiryState) -> str:
        summary = self.summary_message(state)
        return (
            "Thank you. I have your details and can send this enquiry to our team "
            "so they can confirm availability and pricing.\n\n"
            f"{summary}"
        )

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        return bool(re.fullmatch(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", email.strip(), re.I))

    @staticmethod
    def _is_valid_phone(phone: str) -> bool:
        digits = re.sub(r"\D", "", phone)
        return len(digits) >= 8

    def detect_urgent_travel(self, message: str) -> bool:
        text = message.lower()
        urgent_phrases = (
            "urgent",
            "asap",
            "as soon as possible",
            "landing soon",
            "arriving soon",
            "last minute",
            "last-minute",
            "right now",
            "tonight",
            "this evening",
            "today",
            "within 24",
            "within 48",
            "next few hours",
            "couple of hours",
            "few hours",
        )
        if any(phrase in text for phrase in urgent_phrases):
            return True
        hour_match = re.search(r"\b(?:in|within)\s+(\d{1,2})\s*hours?\b", text)
        if hour_match and int(hour_match.group(1)) <= 48:
            return True
        return bool(re.search(r"\b(?:in|within)\s+(\d{1,2})\s*mins?\b", text))

    def is_informational_question(self, message: str) -> bool:
        text = message.lower().strip()
        if self.wants_team_handover(text):
            return False
        info_markers = (
            "walk me through",
            "how does",
            "how do",
            "what cars",
            "which cars",
            "what vehicles",
            "what is included",
            "what's included",
            "explain",
            "tell me about",
            "steps",
            "process",
            "how it works",
            "policy",
            "policies",
            "difference between",
            "do you offer",
            "what services",
        )
        if any(marker in text for marker in info_markers):
            return True
        if text.endswith("?") and not any(
            token in text
            for token in (
                "book",
                "arrange",
                "need",
                "want",
                "passengers",
                "transfer",
                "change",
                "update",
            )
        ):
            return True
        return False

    def looks_like_booking_change(self, message: str) -> bool:
        if self.is_informational_question(message):
            return False
        text = message.lower()
        change_markers = (
            "change",
            "update",
            "instead",
            "make it",
            "passengers",
            "passenger",
            "add a",
            "another person",
            "different date",
            "different time",
            "vehicle",
            "car type",
            "luxury car",
            "pickup",
            "drop-off",
            "drop off",
            "airport",
            "terminal",
        )
        if any(marker in text for marker in change_markers):
            return True
        return self.detect_intent(message) != EnquiryType.NONE

    def urgent_contact_message(self) -> str:
        return (
            "Because this looks like a last-minute request (within 24–48 hours), "
            "please contact our operations desk directly for real-time confirmation "
            "on WhatsApp +44 7414 246103 rather than waiting for an email reply."
        )

    def strip_enquiry_upsell(self, answer: str) -> str:
        if not answer:
            return answer
        patterns = (
            r"(?:\n+)?Would you like me to add this to your current enquiry\??",
            r"(?:\n+)?Shall I add this to your (?:current )?enquiry\??",
            r"(?:\n+)?Would you like (?:me )?to (?:update|add this to) your enquiry\??",
            r"(?:\n+)?Can I add this to your enquiry\??",
        )
        cleaned = answer
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.I)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

    def informational_closing(self) -> str:
        return "Does this help, or do you have any other questions about your upcoming trip?"

    def wants_team_handover(self, message: str) -> bool:
        text = message.lower()
        phrases = (
            "pass this",
            "pass it to",
            "pass the enquiry",
            "pass this complete",
            "send this to the team",
            "send it to the team",
            "send this over",
            "submit an enquiry",
            "submit the enquiry",
            "submit enquiry",
            "hand this over",
            "handover",
            "over to your team",
            "over to the team",
            "forward this",
            "give this to the team",
        )
        return any(phrase in text for phrase in phrases)

    def claims_team_handover(self, answer: str) -> bool:
        text = answer.lower()
        phrases = (
            "passed your enquiry",
            "passed this enquiry",
            "successfully passed",
            "will be in touch",
            "will get in touch",
            "team will review",
            "team will contact",
            "handed over to our team",
            "passed over to our team",
            "sent your enquiry",
            "sent this over to our team",
            "submitted your enquiry",
        )
        return any(phrase in text for phrase in phrases)

    def contact_needed_message(self, state: EnquiryState) -> str:
        has_name = bool(state.enquiry_type != EnquiryType.NONE and self._field_value(state, "passenger_name"))
        has_email = bool(state.enquiry_type != EnquiryType.NONE and self._field_value(state, "contact_email"))
        has_phone = bool(state.enquiry_type != EnquiryType.NONE and self._field_value(state, "contact_phone"))

        if has_name and (has_email or has_phone):
            return (
                "Thank you. I have your contact details and can send this enquiry to our team "
                "so they can reach you."
            )

        if not has_name and not has_email and not has_phone:
            return (
                "Before I send this over to our team, could you please share your full name "
                "and email address (or phone number) so they can reach you?"
            )
        if not has_name:
            return (
                "Before I send this over to our team, could you please share your full name "
                "so they know who to contact?"
            )
        if not has_email and not has_phone:
            return (
                "Before I send this over to our team, could you please share your email address "
                "(or a phone / WhatsApp number) so they can reach you?"
            )
        return (
            "Before I send this over to our team, could you please share your full name "
            "and email address (or phone number) so they can reach you?"
        )

    def contact_reminder_message(self, state: EnquiryState) -> str:
        has_name = bool(state.enquiry_type != EnquiryType.NONE and self._is_valid_name(self._field_value(state, "passenger_name")))
        has_email = bool(
            state.enquiry_type != EnquiryType.NONE
            and self._field_value(state, "contact_email")
            and self._is_valid_email(str(self._field_value(state, "contact_email")))
        )
        has_phone = bool(
            state.enquiry_type != EnquiryType.NONE
            and self._field_value(state, "contact_phone")
            and self._is_valid_phone(str(self._field_value(state, "contact_phone")))
        )
        missing: list[str] = []
        if not has_name:
            missing.append("your full name")
        if not has_email and not has_phone:
            missing.append("an email address or phone number")
        elif not has_email:
            missing.append("an email address")
        needed = " and ".join(missing) if missing else "your contact details"
        return (
            f"I still need {needed} before I can send this to the team. "
            "Please reply with those details when you are ready."
        )

    def already_asked_for_contact(self, messages: list[dict[str, str]]) -> bool:
        markers = (
            "before i send this over to our team",
            "share your full name",
            "email address (or phone",
            "i still need",
        )
        for item in reversed(messages[-6:]):
            if item.get("role") != "assistant":
                continue
            text = (item.get("content") or "").lower()
            if any(marker in text for marker in markers):
                return True
        return False

    def is_contact_repeat_complaint(self, message: str) -> bool:
        text = message.lower()
        phrases = (
            "again and again",
            "again and agin",
            "baar baar",
            "why you ask",
            "why are you asking",
            "keep asking",
            "asked me name",
            "ask me name",
            "already gave",
            "already told",
            "already shared",
        )
        return any(phrase in text for phrase in phrases)

    def contact_repeat_apology(self, state: EnquiryState) -> str:
        has_name = bool(state.enquiry_type != EnquiryType.NONE and self._is_valid_name(self._field_value(state, "passenger_name")))
        has_contact = self.has_team_contact(state)
        if has_contact:
            return (
                "Apologies for repeating that. I already have your contact details, "
                "so I will not ask again."
            )
        if has_name:
            return (
                "Sorry about that — I will not keep asking for your name. "
                "I only still need an email address or phone number so the team can reach you."
            )
        return (
            "Sorry for repeating myself. I only need your full name and an email or phone number "
            "once, so the team can reach you when you want this enquiry sent over. "
            "Whenever you are ready, please share those details."
        )

    def sanitize_false_handover(self, answer: str) -> str:
        if not answer:
            return answer
        cleaned = answer
        patterns = (
            r"(?i)I have successfully passed[^.!\n]*[.!]?",
            r"(?i)I(?:'ve| have) (?:passed|submitted|sent|handed)[^.!\n]*(?:team|enquiry)[^.!\n]*[.!]?",
            r"(?i)(?:They|Our team) will (?:be in touch|get in touch|contact you|review)[^.!\n]*[.!]?",
            r"(?i)passed your enquiry[^.!\n]*[.!]?",
            r"(?i)submitted your enquiry[^.!\n]*[.!]?",
        )
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

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
        collected = self._human_details(enquiry) or "None yet."
        can_contact = self.has_team_contact(state)
        contact_rule = (
            "Contact details are validated on file (full name + email or phone). "
            "You may confirm that the enquiry can be sent to the team."
            if can_contact
            else (
                "Contact details are MISSING or incomplete. You must NOT say the enquiry has been "
                "passed, submitted, or sent to the team, and you must NOT say they will be in touch. "
                "Ask for full name and email/phone only when the user wants to send the enquiry to the team. "
                "Do not repeat the same contact request on every message."
            )
        )
        return (
            f"Active {label}.\n"
            f"Collected details (already known — do NOT re-ask these):\n{collected}\n"
            f"Next missing detail only: {missing_text}\n"
            f"{contact_rule}\n"
            "Do not confirm a booking. Treat this as an enquiry or booking request.\n"
            "Never ask 'Would you like me to add this to your current enquiry?' after informational answers.\n"
            "Never print dictionaries, JSON, Python objects, or raw field names in the reply."
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

        lines = self._human_details(details)
        if not lines:
            return (
                f"I've got the details for your {service} enquiry. "
                "Our team can confirm availability and the final price."
            )
        return (
            f"I've got the details for your {service} enquiry. "
            "Our team can confirm availability and the final price.\n\n"
            f"{lines}"
        )

    @staticmethod
    def _human_details(details: dict[str, Any]) -> str:
        labels = {
            "airport": "Airport",
            "pickup_location": "Pickup",
            "dropoff_location": "Drop-off",
            "service_date": "Date",
            "service_time": "Time",
            "flight_number": "Flight",
            "passenger_count": "Passengers",
            "passenger_name": "Lead passenger",
            "contact_email": "Email",
            "contact_phone": "Phone",
            "luggage_details": "Luggage",
            "special_requirements": "Notes",
        }
        lines: list[str] = []
        for key, label in labels.items():
            value = details.get(key)
            if value in (None, "", {}, []):
                continue
            lines.append(f"- {label}: {value}")
        return "\n".join(lines)

    def _update_model(
        self,
        model: AirportVipEnquiry | AirportTransferEnquiry,
        message: str,
        fields: tuple[tuple[str, str], ...],
    ) -> None:
        text = message.strip()
        if not text:
            return

        structured = {
            "airport",
            "service_date",
            "service_time",
            "passenger_count",
            "contact_email",
            "contact_phone",
            "passenger_name",
        }
        # Structured values can be pulled from any message in parallel.
        for field_name, _ in fields:
            if field_name not in structured:
                continue
            if getattr(model, field_name):
                continue
            value = self._extract_field_value(field_name, text)
            if value is not None:
                setattr(model, field_name, value)

        # Ambiguous short answers fill only the next empty free-text slot.
        free_text = {
            "pickup_location",
            "dropoff_location",
            "flight_number",
            "luggage_details",
            "special_requirements",
        }
        for field_name, _ in fields:
            if field_name not in free_text:
                continue
            if getattr(model, field_name):
                continue
            value = self._extract_field_value(field_name, text)
            if value is not None:
                setattr(model, field_name, value)
                break

    def _extract_field_value(self, field_name: str, text: str) -> Any:
        lowered = text.lower().strip()

        if field_name == "passenger_count":
            match = re.search(
                r"\b(\d{1,2})\s*(?:passengers?|pax|people|persons?)\b",
                lowered,
            )
            if match:
                return int(match.group(1))
            match = re.search(r"\bfor\s+(\d{1,2})\b", lowered)
            if match:
                return int(match.group(1))
            if "just me" in lowered or "only me" in lowered:
                return 1
            if re.fullmatch(r"\d{1,2}", text.strip()):
                return int(text.strip())

        if field_name == "contact_email":
            match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
            if match:
                return match.group(0)

        if field_name == "contact_phone":
            match = re.search(r"(\+?\d[\d\s\-()]{7,}\d)", text)
            if match:
                return match.group(0).strip()

        if field_name == "airport":
            return self._extract_airport(text)

        if field_name == "service_date":
            return self._extract_date(text)

        if field_name == "service_time":
            return self._extract_time(text)

        if field_name == "passenger_name":
            return self._extract_name(text)

        if field_name == "flight_number":
            match = re.search(
                r"(?:flight\s*(?:number|no\.?|#)?\s*[:=]?\s*)([A-Z]{1,3}\s?\d{2,4})\b",
                text,
                re.I,
            )
            if match:
                return re.sub(r"\s+", "", match.group(1)).upper()
            match = re.search(r"\b([A-Z]{2,3}\s?\d{2,4})\b", text, re.I)
            if match and ("flight" in lowered or re.fullmatch(r"[A-Za-z]{2,3}\s?\d{2,4}", text.strip())):
                return re.sub(r"\s+", "", match.group(1)).upper()
            if re.fullmatch(r"[A-Za-z]{1,3}\s?\d{2,4}", text.strip()):
                return re.sub(r"\s+", "", text.strip()).upper()

        if field_name == "luggage_details":
            match = re.search(
                r"\b(\d{1,2})\s*(?:bags?|suitcases?|pieces?(?:\s+of\s+luggage)?|luggage)\b",
                lowered,
            )
            if match:
                return f"{match.group(1)} bags"
            if "no bags" in lowered or "no luggage" in lowered:
                return "0 bags"
            if re.fullmatch(r"\d{1,2}", text.strip()):
                return f"{text.strip()} bags"
            if len(text.split()) <= 6 and any(
                token in lowered for token in ("bag", "luggage", "suitcase", "piece")
            ):
                return text.strip()
            return None

        if field_name in {
            "pickup_location",
            "dropoff_location",
            "special_requirements",
        }:
            if self._looks_like_intent_only(lowered):
                return None
            if self._extract_airport(text) and len(text.split()) <= 4:
                # Pure airport answers belong to the airport slot, not pickup/drop-off.
                return None
            if self._contains_contact_or_count_noise(lowered):
                return None
            if field_name == "pickup_location":
                match = re.search(r"(?:pick(?:\s*up)?\s*(?:from)?|from)\s+(.+)$", text, re.I)
                if match:
                    return match.group(1).strip(" .,")
            if field_name == "dropoff_location":
                match = re.search(r"(?:drop(?:\s*-?\s*off)?(?:\s*at)?|to)\s+(.+)$", text, re.I)
                if match:
                    return match.group(1).strip(" .,")
            if len(text.split()) <= 6:
                return text.strip()

        return None

    @staticmethod
    def _extract_date(text: str) -> str | None:
        patterns = (
            r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
            r"\b(?:\d{1,2}(?:st|nd|rd|th)?\s+)?(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|"
            r"apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
            r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
            r"(?:\s+\d{1,2}(?:st|nd|rd|th)?)?(?:\s+\d{4})?\b",
            r"\b(?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            r"\b(?:today|tomorrow)\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group(0)

        lowered = text.lower().strip()
        if BookingService._looks_like_intent_only(lowered):
            return None
        if len(text.split()) <= 4 and not re.search(r"@|\+\d|\d{1,2}:\d{2}", text):
            # Short free-text date answers like "10 May 2026" already covered;
            # allow other short date-like replies only if they include a digit or weekday.
            if re.search(r"\d|mon|tue|wed|thu|fri|sat|sun|today|tomorrow|may|june|july", lowered):
                return text.strip()
        return None

    @staticmethod
    def _extract_time(text: str) -> str | None:
        match = re.search(
            r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)|"
            r"\d{1,2}:\d{2})\b",
            text,
            re.I,
        )
        if match:
            return match.group(0).strip()
        match = re.search(r"\b(\d{1,2})\s*(?:o'?clock)\b", text, re.I)
        if match:
            return match.group(0).strip()
        return None

    @staticmethod
    def _looks_like_intent_only(lowered: str) -> bool:
        return any(noise in lowered for noise in INTENT_NOISE) and len(lowered.split()) <= 14

    @staticmethod
    def _contains_contact_or_count_noise(lowered: str) -> bool:
        return bool(
            "@" in lowered
            or re.search(r"\+?\d[\d\s\-()]{7,}\d", lowered)
            or re.search(r"\b\d{1,2}\s*(?:passengers?|pax)\b", lowered)
        )
