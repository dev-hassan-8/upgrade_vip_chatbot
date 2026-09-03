from __future__ import annotations

import re

CONTACT_EMAIL = "avip@upgradevip.com"
CONTACT_WHATSAPP = "+44 7414 246103"
CONTACT_LINE = f"Email: {CONTACT_EMAIL} or WhatsApp: {CONTACT_WHATSAPP}"

# Airports/cities explicitly named in knowledge_base/upgradevip_details.txt
KB_NAMED_AIRPORTS: dict[str, str] = {
    "heathrow": "Heathrow",
    "lhr": "Heathrow",
    "jfk": "JFK",
    "new york jfk": "JFK",
    "paris": "Paris",
    "charles de gaulle": "Paris",
    "cdg": "Paris",
    "dubai": "Dubai",
    "dxb": "Dubai",
    "singapore": "Singapore Changi",
    "changi": "Singapore Changi",
    "frankfurt": "Frankfurt",
    "fra": "Frankfurt",
    "mumbai": "Mumbai",
    "bom": "Mumbai",
    "lax": "Los Angeles (LAX)",
    "los angeles": "Los Angeles (LAX)",
    "cmh": "John Glenn Columbus (CMH)",
    "columbus": "John Glenn Columbus (CMH)",
    "fnc": "Madeira (FNC)",
    "madeira": "Madeira (FNC)",
    "yyz": "Toronto Pearson (YYZ)",
    "toronto": "Toronto Pearson (YYZ)",
    "pearson": "Toronto Pearson (YYZ)",
}

# Common airports people ask about that are NOT specifically confirmed in the KB
COMMON_UNLISTED_AIRPORTS: dict[str, str] = {
    "gatwick": "London Gatwick",
    "lgw": "London Gatwick",
    "stansted": "London Stansted",
    "stn": "London Stansted",
    "luton": "London Luton",
    "ltn": "London Luton",
    "london city": "London City",
    "lcy": "London City",
    "manchester": "Manchester",
    "man": "Manchester",
    "birmingham": "Birmingham",
    "bhx": "Birmingham",
    "edinburgh": "Edinburgh",
    "edi": "Edinburgh",
    "glasgow": "Glasgow",
    "gla": "Glasgow",
    "dublin": "Dublin",
    "dub": "Dublin",
    "orly": "Paris Orly",
    "ory": "Paris Orly",
    "schiphol": "Amsterdam Schiphol",
    "ams": "Amsterdam Schiphol",
    "lahore": "Lahore",
    "lhe": "Lahore",
    "islamabad": "Islamabad",
    "isb": "Islamabad",
    "karachi": "Karachi",
    "khi": "Karachi",
}

CONTACT_ONLY_SERVICES: dict[str, tuple[str, ...]] = {
    "hotel": ("hotel", "hotels", "book a hotel", "hotel booking", "hotel reservation"),
    "tour": ("tour booking", "book a tour", "tours", "sightseeing tour"),
    "bodyguard": ("bodyguard", "bodyguards", "security guard", "personal protection"),
    "helicopter": ("helicopter", "heli charter", "private helicopter"),
    "private_jet": ("private jet", "jet charter", "charter a jet", "private plane"),
}

SERVICE_LABELS = {
    "hotel": "hotel bookings",
    "tour": "tour bookings",
    "bodyguard": "bodyguard services",
    "helicopter": "helicopter charters",
    "private_jet": "private jet charters",
}


class GroundingService:
    """KB-aligned grounding helpers to reduce unsupported claims."""

    def detect_contact_only_service(self, message: str) -> str | None:
        text = message.lower()
        # Prefer longer / more specific matches first
        for service, patterns in CONTACT_ONLY_SERVICES.items():
            if any(pattern in text for pattern in patterns):
                return service
        return None

    def asks_about_pricing(self, message: str) -> bool:
        text = message.lower()
        if any(marker in text for marker in ("price", "pricing", "how much", "discount", "discounts", "cheap", "expensive", "£", "$")):
            return True
        return bool(
            re.search(r"\b(cost|costs|fee|fees|rate|rates|quote|quotes)\b", text)
        )

    def asks_about_terminal(self, message: str) -> bool:
        return bool(re.search(r"\bterminals?\b", message.lower()))

    def asks_about_guarantee(self, message: str) -> bool:
        text = message.lower()
        if "travel delight" in text or "delight guarantee" in text:
            return True
        if "guarantee" not in text:
            return False
        # "Can you guarantee wheelchair/fast-track..." is operational, not Travel Delight.
        operational = (
            "wheelchair",
            "prm",
            "assistance",
            "fast track",
            "fast-track",
            "security",
            "every airport",
            "at every",
            "terminal",
            "arrival",
            "transfer",
            "pickup",
        )
        if any(token in text for token in operational):
            return False
        return True

    def asks_about_concierge_employment(self, message: str) -> bool:
        text = message.lower()
        employment = ("employee", "employees", "employ", "staff", "hire", "hired", "work for you")
        concierge = ("concierge", "concierges", "20000", "20,000", "20 000")
        return any(e in text for e in employment) and any(c in text for c in concierge)

    def asks_about_partnerships_or_ownership(self, message: str) -> bool:
        text = message.lower()
        markers = (
            "partner with",
            "partnership",
            "own the lounge",
            "own lounges",
            "lounge ownership",
            "airline partner",
            "airport authority",
            "do you own",
            "your lounge",
            "operate the lounge",
        )
        return any(marker in text for marker in markers)

    def find_unconfirmed_airports(self, message: str) -> list[str]:
        text = message.lower()
        found: list[str] = []
        # Longer keys first to avoid partial overlaps
        for key, label in sorted(COMMON_UNLISTED_AIRPORTS.items(), key=lambda item: len(item[0]), reverse=True):
            if re.search(rf"\b{re.escape(key)}\b", text):
                if label not in found:
                    found.append(label)
        return found

    def find_confirmed_airports(self, message: str) -> list[str]:
        text = message.lower()
        found: list[str] = []
        for key, label in sorted(KB_NAMED_AIRPORTS.items(), key=lambda item: len(item[0]), reverse=True):
            if re.search(rf"\b{re.escape(key)}\b", text):
                if label not in found:
                    found.append(label)
        return found

    def boost_retrieval_query(self, message: str) -> str:
        """Append KB section keywords so the right grounding chunks are retrieved."""
        extras: list[str] = []
        service = self.detect_contact_only_service(message)
        if service:
            extras.extend(
                [
                    "bot capabilities",
                    "booking options",
                    SERVICE_LABELS[service],
                    "avip@upgradevip.com",
                ]
            )
        if self.asks_about_pricing(message):
            extras.extend(["pricing", "cost", "fixed rates", "quotes", "booking contact"])
        if self.asks_about_guarantee(message):
            extras.extend(["Travel Delight Guarantee", "in-house concierge", "service fee"])
        if self.asks_about_concierge_employment(message):
            extras.extend(["20,000 concierges", "trusted local operators", "licensed insured"])
        if self.asks_about_partnerships_or_ownership(message):
            extras.extend(["partnerships", "local operators", "lounge services", "experience"])
        if self.find_unconfirmed_airports(message) or self.asks_about_terminal(message):
            extras.extend(["350+ airports worldwide", "global availability", "featured airports"])
        if not extras:
            return message
        return f"{message} {' '.join(extras)}"

    def build_grounding_directives(self, message: str) -> str:
        lines: list[str] = [
            "GROUNDING DIRECTIVES (must follow):",
            "- Use ONLY facts present in KNOWLEDGE BASE CONTEXT. Do not invent or assume missing details.",
            "- If something is not in the context, say the specific information is not available.",
            f"- Official contact when needed: {CONTACT_LINE}.",
            "- Answer every part of the user's question.",
            "- Never claim the customer already provided details that are not in CONVERSATION HISTORY / ENQUIRY STATE.",
        ]

        unconfirmed = self.find_unconfirmed_airports(message)
        if unconfirmed:
            names = ", ".join(unconfirmed)
            lines.append(
                f"- Airport check: {names} is/are NOT specifically named in the knowledge base. "
                "Do NOT confirm UpgradeVIP operates there. Say available information confirms "
                "350+ airports worldwide but does not specifically confirm that airport. "
                "You may still offer to take an Airport VIP / Transfer enquiry or share contact details."
            )
        elif self.find_confirmed_airports(message):
            lines.append(
                "- Airport check: the named airport appears among knowledge-base examples/featured hubs. "
                "You may acknowledge that example coverage, without inventing terminals or procedures."
            )

        if self.asks_about_terminal(message):
            lines.append(
                "- Terminal check: do NOT confirm any specific terminal (e.g. Terminal 2) unless that "
                "exact terminal is stated in the knowledge base context. The KB only notes domestic/"
                "international terminal coverage in general."
            )

        service = self.detect_contact_only_service(message)
        if service:
            label = SERVICE_LABELS[service]
            lines.append(
                f"- Booking capability: this chatbot cannot directly book {label}. "
                f"State that clearly and direct the customer to {CONTACT_LINE}. "
                "Do not claim you can book it here."
            )

        if self.asks_about_pricing(message):
            lines.append(
                "- Pricing: the knowledge base does not publish specific prices or discounts. "
                "Do not invent amounts or discounts. Explicitly say pricing/discount details are not "
                f"available here and direct the customer to {CONTACT_LINE}. Answer BOTH cost and "
                "discount parts if both were asked."
            )

        if self.asks_about_guarantee(message):
            lines.append(
                "- Travel Delight Guarantee: use ONLY the KB wording (in-house concierge team, "
                "5-day / 1 business day response standard, repay service fee). Do not add third-party "
                "supplier conditions that are not in that guarantee text."
            )

        if self.asks_about_concierge_employment(message):
            lines.append(
                "- Concierges: KB says a network of 20,000 concierges and partnership with licensed/"
                "insured/trusted local operators. Do NOT claim all 20,000 are UpgradeVIP employees."
            )

        if self.asks_about_partnerships_or_ownership(message):
            lines.append(
                "- Partnerships/ownership: do not invent airline, lounge ownership, airport-authority, "
                "or named supplier arrangements. Only use what the KB states (e.g. Fortune 500 / FTSE 100 "
                "/ TMC / luxury travel categories; licensed local operators; lounge access as a service)."
            )

        return "\n".join(lines)

    def contact_only_fallback(self, service: str) -> str:
        label = SERVICE_LABELS.get(service, "that service")
        return (
            f"I can help directly with Airport VIP Services and Airport Transfers in this chat. "
            f"For {label}, please contact our team on {CONTACT_LINE}."
        )

    def pricing_fallback(self) -> str:
        return (
            "Specific pricing and discount details are not available in the information I have here. "
            f"For an accurate quote, please contact {CONTACT_LINE}."
        )

    def ensure_answer_covers_grounding(self, message: str, answer: str) -> str:
        """Post-check: fill critical gaps if the model skipped required grounding."""
        if not answer:
            answer = ""
        text = answer.lower()
        parts: list[str] = [answer.strip()] if answer.strip() else []

        service = self.detect_contact_only_service(message)
        if service:
            label = SERVICE_LABELS[service]
            claims_can_book = any(
                phrase in text
                for phrase in (
                    f"i can book your {label.split()[0]}",
                    "i'll book",
                    "i will book",
                    "book that for you",
                    "book this for you",
                    "i can arrange that here",
                    "i can book that here",
                )
            )
            if claims_can_book or CONTACT_EMAIL.lower() not in text:
                parts = [self.contact_only_fallback(service)]

        if self.asks_about_pricing(message):
            joined = " ".join(parts)
            joined_lower = joined.lower()
            has_contact = CONTACT_EMAIL in joined_lower or "7414 246103" in joined
            invents_price = bool(
                re.search(r"(£\s*\d|\$\s*\d|\d+\s*(%|gbp|usd|pounds|dollars))", joined, re.I)
            )
            mentions_unavailable = any(
                phrase in joined_lower
                for phrase in (
                    "not available",
                    "do not have",
                    "don't have",
                    "no specific price",
                    "no specific pricing",
                    "pricing is not",
                    "price is not",
                    "prices are not",
                    "discount details are not",
                    "discounts are not",
                )
            )
            needs_pricing_fix = invents_price or not mentions_unavailable or not has_contact
            if needs_pricing_fix:
                if "discount" in message.lower():
                    pricing = (
                        "Specific pricing and any discount details are not available in the "
                        f"information I have here. For an accurate quote, please contact {CONTACT_LINE}."
                    )
                else:
                    pricing = self.pricing_fallback()
                if invents_price or not mentions_unavailable:
                    parts = [pricing]
                else:
                    parts.append(pricing)
        unconfirmed = self.find_unconfirmed_airports(message)
        if unconfirmed:
            joined = " ".join(parts).lower()
            falsely_confirms = any(
                phrase in joined
                for phrase in (
                    "yes, we operate",
                    "we do operate at",
                    "we operate at",
                    "we cover",
                    "we serve",
                    "available at",
                    "yes we cover",
                    "confirmed at",
                )
            )
            hedges = any(
                phrase in joined
                for phrase in (
                    "does not specifically confirm",
                    "not specifically confirm",
                    "350+",
                    "350 +",
                    "not available",
                    "cannot specifically confirm",
                    "don't specifically confirm",
                    "do not specifically confirm",
                )
            )
            if falsely_confirms or not hedges:
                names = ", ".join(unconfirmed)
                airport_note = (
                    f"Our available information confirms UpgradeVIP operates at 350+ airports worldwide, "
                    f"but it does not specifically confirm coverage at {names}. "
                    f"For confirmation, please contact {CONTACT_LINE}."
                )
                if falsely_confirms:
                    parts = [airport_note]
                else:
                    parts.append(airport_note)

        if self.asks_about_terminal(message):
            joined = " ".join(parts).lower()
            invents_terminal = bool(
                re.search(r"terminal\s*\d|we (do )?operate(s)? (in|at) terminal", joined)
            ) and "does not specifically" not in joined
            if invents_terminal or (
                "terminal" in message.lower()
                and "specifically" not in joined
                and "350+" not in joined
                and "not available" not in joined
            ):
                terminal_note = (
                    "Our available information notes coverage across domestic and international terminals "
                    "in general, but it does not specifically confirm any individual terminal. "
                    f"For confirmation, please contact {CONTACT_LINE}."
                )
                if invents_terminal:
                    parts = [terminal_note]
                elif terminal_note.lower() not in joined:
                    parts.append(terminal_note)

        if self.asks_about_concierge_employment(message):
            joined = " ".join(parts).lower()
            claims_all_employees = bool(
                re.search(
                    r"(all|every).{0,40}(concierge|20,?000).{0,40}(employee|staff|work for)",
                    joined,
                )
            ) or bool(
                re.search(r"(are|is) (all |direct )?(upgradevip )?employees", joined)
            )
            grounded = any(
                phrase in joined
                for phrase in (
                    "local operator",
                    "local operators",
                    "network of",
                    "does not say",
                    "do not claim",
                    "not say that all",
                )
            )
            if claims_all_employees or not grounded:
                parts = [
                    "UpgradeVIP works with a network of 20,000 concierges and partners with licensed, "
                    "insured and trusted local operators. The available information does not say that "
                    "all 20,000 concierges are direct UpgradeVIP employees. "
                    f"For more detail, contact {CONTACT_LINE}."
                ]

        if self.asks_about_partnerships_or_ownership(message):
            joined = " ".join(parts).lower()
            invents_named_partner = bool(
                re.search(
                    r"\b(british airways|ba lounges?|airline partner|own(s|ed)? (the )?lounge|airport authority)\b",
                    joined,
                )
            )
            grounded = any(
                phrase in joined
                for phrase in (
                    "does not confirm",
                    "do not confirm",
                    "not available",
                    "not specifically",
                    "fortune 500",
                    "ftse",
                    "local operator",
                    "lounge access",
                )
            )
            if invents_named_partner or not grounded:
                parts = [
                    "The available information does not confirm lounge ownership or named airline/"
                    "airport-authority partnerships. It states UpgradeVIP works with Fortune 500, "
                    "FTSE 100, top TMCs and luxury travel companies, and partners with licensed, "
                    "insured local operators, while lounge access is offered as part of Airport VIP "
                    f"services. For specifics, contact {CONTACT_LINE}."
                ]
        if self.asks_about_guarantee(message):
            joined = " ".join(parts).lower()
            invents_extra = any(
                phrase in joined
                for phrase in (
                    "third-party supplier",
                    "third party supplier",
                    "supplier policies",
                    "supplier policy",
                )
            )
            has_core = "travel delight" in joined or "service fee" in joined or "in-house concierge" in joined
            if invents_extra or not has_core:
                parts = [
                    "Under the Travel Delight Guarantee, UpgradeVIP’s in-house concierge team aims to "
                    "deliver a high standard of service. If within 5 days after the service date you "
                    "feel the team has not responded to requests within 1 business day, or has not met "
                    "agreed service standards, UpgradeVIP will promptly repay the service fee. "
                    "Please rely only on that documented guarantee wording. "
                    f"For questions, contact {CONTACT_LINE}."
                ]

        cleaned = "\n\n".join(part.strip() for part in parts if part and part.strip())
        return re.sub(r"\n{3,}", "\n\n", cleaned).strip()
