from __future__ import annotations

import logging
import math
import re
from collections import Counter

from app.config import Settings, get_settings
from app.models.chat import Source
from app.services.embedding_service import EmbeddingService
from app.vectorstore.base import RetrievedChunk, VectorStore
from app.vectorstore.factory import get_vector_store

logger = logging.getLogger(__name__)

CONVERSATIONAL_PATTERNS = (
    r"^(hi|hello|hey|hiya|good morning|good afternoon|good evening)[!. ]*$",
    r"^(thanks|thank you|cheers|much appreciated)[!. ]*$",
    r"^(ok|okay|great|good|perfect|lovely|brilliant|sounds good)[!. ]*$",
    r"^(bye|goodbye|see you|take care)[!. ]*$",
    r"^(you're great|you are great|well done)[!. ]*$",
)

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "so", "to", "of", "in", "on",
    "at", "for", "from", "with", "into", "over", "after", "before", "between",
    "is", "are", "was", "were", "be", "been", "being", "am", "do", "does", "did", "doing",
    "can", "could", "would", "should", "will", "shall", "may", "might", "must",
    "i", "me", "my", "we", "our", "you", "your", "they", "them", "their", "it", "its",
    "this", "that", "these", "those", "there", "here", "what", "which", "who", "whom",
    "how", "when", "where", "why", "as", "by", "not", "no", "yes", "please", "thanks",
    "thank", "also", "just", "only", "very", "more", "most", "some", "any", "all",
    "every", "each", "other", "than", "too", "out", "up", "down", "off", "again",
    "further", "once", "have", "has", "had", "having", "get", "got", "make", "made",
    "tell", "know",
}

# Common across many sections — still useful, but weighted down.
LOW_SIGNAL_TERMS = {
    "service", "services", "upgradevip", "upgrade", "company", "team",
    "customer", "clients", "client", "travel", "travelling", "traveling",
    "information", "details", "available", "offer", "offers", "provide", "provides",
    "provided", "help", "assist", "need", "needs", "want", "book", "booking",
}

# Light stem/alias map so "operating" matches "operated", etc.
TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "operating": ("operate", "operated", "operation", "operations"),
    "operate": ("operating", "operated", "operation"),
    "operated": ("operate", "operating", "operation"),
    "cancellation": ("cancel", "cancelled", "canceled", "cancellations"),
    "cancel": ("cancellation", "cancelled", "canceled"),
    "vehicles": ("vehicle", "cars", "car", "suv", "sedan", "chauffeur"),
    "vehicle": ("vehicles", "cars", "car"),
    "certifications": ("certification", "licences", "licenses", "abta", "atol", "iata"),
    "certification": ("certifications", "licences", "licenses", "abta", "atol", "iata"),
    "offices": ("office", "locations", "location"),
    "office": ("offices", "locations"),
    "philosophy": ("values", "beliefs", "5ps", "brand"),
    "included": ("include", "includes", "inclusion", "inclusions"),
    "include": ("included", "includes", "inclusion"),
    "assistance": ("assist", "assisted"),
    "assist": ("assistance", "assisted"),
    "passengers": ("passenger", "pax"),
    "passenger": ("passengers", "pax"),
}

INTENT_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "services": (
        "upgradevip services",
        "airport vip",
        "airport transfers",
        "meet & greet",
        "porter",
        "lounge",
        "chauffeur",
        "concierge",
    ),
    "prm_assistance": (
        "wheelchair",
        "prm",
        "special assistance",
        "elderly",
        "seniors",
        "disabilities",
        "special-needs",
        "porter",
        "meet & greet",
        "airport vip",
    ),
    "fast_track": (
        "fast track",
        "fast-track",
        "security",
        "priority",
        "meet & greet",
        "airport vip",
    ),
    "lounge": (
        "airport vip lounge",
        "lounge access",
        "luxury lounges",
        "airport vip services",
    ),
    "meet_greet": (
        "meet & greet",
        "meet and greet",
        "airport vip",
        "fast track",
    ),
    "porter": (
        "porter service",
        "luggage",
        "airport vip",
    ),
    "airport_coverage": (
        "airports",
        "global availability",
        "350+",
        "terminals",
        "featured airports",
        "jfk",
        "heathrow",
    ),
    "transfers": (
        "airport transfer",
        "private transfer",
        "chauffeur",
        "fixed rates",
        "transportation",
        "suv",
        "sedan",
    ),
    "pricing": (
        "pricing",
        "cost",
        "quote",
        "fixed rates",
        "modular quotes",
        "contact",
    ),
    "booking_capabilities": (
        "bot capabilities",
        "airport vip service",
        "airport transfers",
        "hotel",
        "private jet",
        "helicopter",
        "bodyguard",
        "avip@upgradevip.com",
    ),
    "hotel": ("hotel booking", "bot capabilities", "avip@upgradevip.com"),
    "tour": ("tour booking", "bot capabilities", "avip@upgradevip.com"),
    "bodyguard": ("bodyguard", "bot capabilities", "avip@upgradevip.com"),
    "helicopter": ("helicopter", "bot capabilities", "avip@upgradevip.com"),
    "private_jet": ("private jet", "bot capabilities", "avip@upgradevip.com"),
    "travel_delight_guarantee": (
        "travel delight guarantee",
        "in-house concierge",
        "service fee",
        "1 business day",
        "terms & conditions",
    ),
    "terms": (
        "terms & conditions",
        "cancellation",
        "refund",
        "booking",
        "payment",
        "liability",
    ),
    "privacy": (
        "privacy policy",
        "gdpr",
        "data protection",
        "personal information",
    ),
    "company": (
        "brand philosophy",
        "mission",
        "partnerships",
        "fortune 500",
        "local operators",
        "since 2009",
        "5ps",
    ),
    "who_uses": (
        "who uses",
        "business executives",
        "luxury travelers",
        "celebrities",
        "special-needs",
    ),
    "contact": (
        "contact",
        "avip@upgradevip.com",
        "whatsapp",
        "offices",
        "abta",
        "atol",
        "iata",
    ),
    "social": (
        "social media",
        "facebook",
        "linkedin",
        "instagram",
    ),
}

INTENT_SECTION_PREFERENCE: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "services": (
        ("upgradevip services", "what are airport vip", "services in detail", "bot capabilities"),
        ("privacy", "copyright", "social media"),
    ),
    "prm_assistance": (
        ("vip", "services", "who uses", "meet", "porter", "concierge"),
        ("terms & conditions", "travel delight", "privacy", "copyright", "social media"),
    ),
    "fast_track": (
        ("vip", "services", "meet", "global availability"),
        ("terms & conditions", "travel delight", "privacy", "copyright"),
    ),
    "lounge": (
        ("lounge", "services", "airport vip"),
        ("privacy", "copyright", "social media", "terms & conditions"),
    ),
    "meet_greet": (
        ("meet", "services", "mission", "airport vip"),
        ("privacy", "copyright", "social media"),
    ),
    "porter": (
        ("porter", "services", "luggage"),
        ("privacy", "copyright", "social media"),
    ),
    "airport_coverage": (
        ("global availability", "featured airports", "mission"),
        ("privacy", "copyright", "social media", "terms & conditions"),
    ),
    "transfers": (
        ("transfer", "chauffeur", "transportation", "services"),
        ("privacy", "copyright", "social media"),
    ),
    "pricing": (
        ("services", "transfer", "terms", "bot capabilities", "contact"),
        ("social media", "copyright", "brand philosophy", "global availability", "featured airports"),
    ),
    "booking_capabilities": (
        ("bot capabilities", "upgradevip services"),
        ("privacy", "copyright", "social media"),
    ),
    "hotel": (("bot capabilities", "upgradevip services"), ("privacy", "copyright")),
    "tour": (("bot capabilities", "upgradevip services"), ("privacy", "copyright")),
    "bodyguard": (("bot capabilities", "upgradevip services"), ("privacy", "copyright")),
    "helicopter": (("bot capabilities", "upgradevip services"), ("privacy", "copyright")),
    "private_jet": (("bot capabilities", "upgradevip services"), ("privacy", "copyright")),
    "travel_delight_guarantee": (
        ("terms & conditions", "mission & guarantee"),
        ("social media", "copyright", "featured airports"),
    ),
    "terms": (
        ("terms & conditions",),
        ("social media", "copyright", "featured airports", "brand philosophy"),
    ),
    "privacy": (
        ("privacy", "gdpr"),
        ("social media", "copyright", "featured airports"),
    ),
    "company": (
        ("about upgradevip", "mission", "experience", "partnerships", "brand"),
        ("social media", "copyright", "privacy", "featured airports", "global availability"),
    ),
    "who_uses": (
        ("who uses",),
        ("privacy", "copyright", "social media", "terms & conditions"),
    ),
    "contact": (
        ("contact", "reach us"),
        (
            "copyright",
            "social media",
            "brand philosophy",
            "global availability",
            "featured airports",
            "who uses",
        ),
    ),
    "social": (("social media",), ("copyright", "terms & conditions")),
}

TRIGGER_LINE = re.compile(r"(?im)^this section answers:\s*(.*)$")
UNAVAILABLE_ANSWER = (
    "I don’t have that exact detail in the information available here. "
    "Our operations desk can confirm it quickly via WhatsApp on +44 7414 246103 "
    "or email at avip@upgradevip.com."
)


class RetrievalService:
    def __init__(
        self,
        settings: Settings | None = None,
        vector_store: VectorStore | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.vector_store = vector_store or get_vector_store(self.settings)
        self.embedding_service = embedding_service or EmbeddingService(self.settings)
        self._idf_cache: dict[str, float] | None = None

    def needs_retrieval(self, message: str, enquiry_active: bool = False) -> bool:
        if enquiry_active:
            return True

        normalized = message.strip().lower()
        if len(normalized) <= 2:
            return False

        for pattern in CONVERSATIONAL_PATTERNS:
            if re.match(pattern, normalized):
                return False

        factual_keywords = (
            "upgradevip",
            "service",
            "services",
            "airport",
            "transfer",
            "vip",
            "book",
            "booking",
            "price",
            "pricing",
            "cost",
            "discount",
            "fee",
            "quote",
            "policy",
            "contact",
            "email",
            "whatsapp",
            "heathrow",
            "gatwick",
            "manchester",
            "terminal",
            "lounge",
            "hotel",
            "tour",
            "bodyguard",
            "helicopter",
            "jet",
            "charter",
            "concierge",
            "employee",
            "partner",
            "partnership",
            "guarantee",
            "wheelchair",
            "prm",
            "assistance",
            "fast-track",
            "fast track",
            "terms",
            "privacy",
            "gdpr",
            "cover",
            "available",
            "offer",
            "provide",
            "operate",
            "operating",
            "philosophy",
            "cancellation",
            "certification",
            "abta",
            "atol",
            "iata",
            "porter",
            "meet",
            "greet",
            "office",
            "licence",
            "license",
        )
        if any(keyword in normalized for keyword in factual_keywords):
            return True

        return len(normalized.split()) >= 4

    def detect_intents(self, query: str) -> list[str]:
        text = query.lower()
        intents: list[str] = []

        if any(k in text for k in ("price", "pricing", "cost", "how much", "discount", "fee", "quote")):
            intents.append("pricing")
        if any(
            k in text
            for k in (
                "wheelchair",
                "prm",
                "special assistance",
                "special-needs",
                "disability",
                "disabilities",
                "elderly passenger",
                "elderly passengers",
            )
        ):
            intents.append("prm_assistance")
        if "fast track" in text or "fast-track" in text or ("security" in text and "airport" in text):
            intents.append("fast_track")
        if "lounge" in text:
            intents.append("lounge")
        if "meet and greet" in text or "meet & greet" in text:
            intents.append("meet_greet")
        if "porter" in text:
            intents.append("porter")
        if "vip terminal" in text or ("terminal access" in text and "vip" in text):
            intents.append("services")
        if any(
            k in text
            for k in (
                "what services",
                "which services",
                "services do you",
                "what do you offer",
                "what do you provide",
                "what's included",
                "what is included",
                "what are included",
                "included in",
                "airport vip service",
                "vip services",
            )
        ):
            intents.append("services")
        if "who uses" in text or "who are your clients" in text or "typical customers" in text:
            intents.append("who_uses")

        coverage_signals = any(
            k in text
            for k in (
                "terminal",
                "which airport",
                "operate at",
                "every airport",
                "at jfk",
                "at heathrow",
                "global coverage",
                "where do you operate",
                "airports do you",
                "airports served",
            )
        )
        # Avoid tagging service-definition questions as coverage.
        if coverage_signals and "services" not in intents and "pricing" not in intents:
            intents.append("airport_coverage")
        elif (
            "airport" in text
            and any(k in text for k in ("cover", "operate at", "available at"))
            and "services" not in intents
            and "pricing" not in intents
        ):
            intents.append("airport_coverage")

        if any(k in text for k in ("transfer", "chauffeur", "pick me up", "drop off", "taxi", "vehicle", "vehicles", "suv", "sedan")):
            intents.append("transfers")
        if "hotel" in text:
            intents.append("hotel")
        if re.search(r"\btours?\b", text) or "tour booking" in text:
            intents.append("tour")
        if "bodyguard" in text:
            intents.append("bodyguard")
        if "helicopter" in text:
            intents.append("helicopter")
        if "private jet" in text or "jet charter" in text:
            intents.append("private_jet")
        if any(k in text for k in ("what can you book", "can i book", "can you book", "bot capabilities")):
            intents.append("booking_capabilities")
        if self._is_travel_delight_guarantee_query(text):
            intents.append("travel_delight_guarantee")
        if any(
            k in text
            for k in (
                "cancellation",
                "cancel",
                "refund",
                "terms and conditions",
                "terms & conditions",
                "liability",
                "payment terms",
            )
        ):
            intents.append("terms")
        if any(k in text for k in ("privacy", "gdpr", "data protection")):
            intents.append("privacy")
        if any(
            k in text
            for k in (
                "about upgradevip",
                "who are you",
                "company",
                "philosophy",
                "partnership",
                "since 2009",
                "how long",
                "operating",
                "established",
                "brand",
                "values",
                "local operators",
            )
        ) or (
            "tell me about" in text
            and not any(intent in {"porter", "lounge", "meet_greet", "transfers", "services", "hotel"} for intent in intents)
        ):
            intents.append("company")
        if any(
            k in text
            for k in (
                "contact",
                "email",
                "whatsapp",
                "phone",
                "office",
                "offices",
                "abta",
                "atol",
                "iata",
                "certification",
                "licence",
                "license",
            )
        ):
            intents.append("contact")
        if any(k in text for k in ("social media", "facebook", "instagram", "linkedin", "twitter")):
            intents.append("social")

        # Default broad service intent for short VIP questions with no other label.
        if not intents and any(k in text for k in ("vip", "airport", "upgradevip", "concierge")):
            intents.append("services")

        seen: set[str] = set()
        ordered: list[str] = []
        for intent in intents:
            if intent not in seen:
                seen.add(intent)
                ordered.append(intent)
        return ordered

    @staticmethod
    def _is_travel_delight_guarantee_query(text: str) -> bool:
        if "travel delight" in text or "delight guarantee" in text:
            return True
        if "guarantee" not in text:
            return False
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
            "pickup",
            "transfer",
        )
        if any(token in text for token in operational):
            return False
        return True

    def expand_queries(self, query: str) -> list[str]:
        intents = self.detect_intents(query)
        variants = [query.strip()]
        for intent in intents:
            expansion = INTENT_EXPANSIONS.get(intent)
            if expansion:
                variants.append(f"{query} {' '.join(expansion)}")
        seen: set[str] = set()
        unique: list[str] = []
        for item in variants:
            key = item.lower()
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique[:5]

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        if self.vector_store.count() == 0:
            logger.warning("Vector store is empty during retrieval.")
            return []

        intents = self.detect_intents(query)
        variants = self.expand_queries(query)
        logger.info("Retrieval intents=%s variants=%s", intents, len(variants))

        keyword_hits = self._keyword_retrieve_multi(variants, intents)
        relevant = self._relevance_gate(query, keyword_hits, intents) if keyword_hits else []

        # If keyword recall is thin, try embeddings and merge.
        if len(relevant) < 2:
            try:
                query_embedding = self.embedding_service.embed_query(variants[0])
                chunks = self.vector_store.query(
                    query_embedding=query_embedding,
                    top_k=max(self.settings.top_k * 3, 10),
                )
                filtered = self._filter_chunks(chunks)
                embed_relevant = self._relevance_gate(query, filtered, intents)
                relevant = self._merge_chunks(relevant, embed_relevant)
            except Exception:
                logger.exception("Embedding fallback failed; using keyword results only")

        if not relevant and keyword_hits:
            # Last-resort recall: keep top keyword hits that are not hard-excluded.
            relevant = self._soft_fallback(query, keyword_hits, intents)

        logger.info("Retrieved %s relevant chunks", len(relevant))
        return relevant[: self.settings.top_k]

    def _merge_chunks(
        self,
        primary: list[RetrievedChunk],
        secondary: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        best: dict[str, RetrievedChunk] = {chunk.id: chunk for chunk in primary}
        for chunk in secondary:
            existing = best.get(chunk.id)
            if existing is None or chunk.score > existing.score:
                best[chunk.id] = chunk
        return sorted(best.values(), key=lambda item: item.score, reverse=True)

    def _keyword_retrieve_multi(
        self,
        queries: list[str],
        intents: list[str],
    ) -> list[RetrievedChunk]:
        best: dict[str, RetrievedChunk] = {}
        for query in queries:
            for chunk in self._keyword_retrieve(query, intents):
                existing = best.get(chunk.id)
                if existing is None or chunk.score > existing.score:
                    best[chunk.id] = chunk
        ranked = sorted(best.values(), key=lambda item: item.score, reverse=True)
        return ranked[: max(self.settings.top_k * 3, 12)]

    def _keyword_retrieve(self, query: str, intents: list[str]) -> list[RetrievedChunk]:
        terms = self._content_terms(query)
        if not terms:
            return []

        idf = self._term_idf()
        scored: list[RetrievedChunk] = []
        for chunk in self.vector_store.get_all():
            section = str(chunk.metadata.get("section", ""))
            body, triggers = self._split_searchable(chunk.text)
            section_l = section.lower()
            body_l = body.lower()
            trigger_l = triggers.lower()

            weighted_matches = 0.0
            matched_content = 0
            matched_any = 0
            for term in terms:
                body_hit = self._term_in_text(term, body_l) or self._term_in_text(term, section_l)
                trigger_hit = self._term_in_text(term, trigger_l)
                if not body_hit and not trigger_hit:
                    continue
                weight = idf.get(term, 1.0)
                if term in LOW_SIGNAL_TERMS:
                    weight *= 0.45
                if body_hit:
                    weighted_matches += weight
                    matched_any += 1
                    if term not in LOW_SIGNAL_TERMS:
                        matched_content += 1
                elif trigger_hit:
                    # Keep section trigger phrases — they exist for retrieval — but lower weight.
                    weighted_matches += weight * 0.55
                    matched_any += 1
                    if term not in LOW_SIGNAL_TERMS:
                        matched_content += 1

            if matched_any == 0:
                continue

            content_terms = [term for term in terms if term not in LOW_SIGNAL_TERMS]
            # Only drop when query has distinctive terms and none matched anywhere.
            if content_terms and matched_content == 0 and not intents:
                continue

            max_weight = sum(
                idf.get(term, 1.0) * (0.45 if term in LOW_SIGNAL_TERMS else 1.0)
                for term in terms
            ) or 1.0
            score = weighted_matches / max_weight
            score *= self._section_intent_multiplier(section, intents)

            lowered_query = query.lower()
            haystack = f"{section_l} {body_l} {trigger_l}"
            if "wheelchair" in lowered_query and "wheelchair" not in haystack:
                if not any(
                    token in haystack
                    for token in ("special assistance", "prm", "elderly", "disabilities", "seniors")
                ):
                    score *= 0.25
            if "travel delight" in lowered_query and "travel delight" in haystack:
                score += 0.3
            if "private jet" in lowered_query and "private jet" in haystack:
                score += 0.25
            if "hotel" in lowered_query and "hotel" in haystack:
                score += 0.25
            if "porter" in lowered_query and "porter" in haystack:
                score += 0.2
            if ("meet and greet" in lowered_query or "meet & greet" in lowered_query) and (
                "meet" in haystack and "greet" in haystack
            ):
                score += 0.2

            chunk.score = min(score, 1.5)
            scored.append(chunk)

        scored.sort(key=lambda item: item.score, reverse=True)
        min_score = min(0.28, max(0.22, self.settings.similarity_threshold - 0.1))
        strong = [chunk for chunk in scored if chunk.score >= min_score]
        return strong[: max(self.settings.top_k * 2, 8)]

    def _relevance_gate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        intents: list[str],
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []

        query_terms = set(self._content_terms(query))
        intent_terms: set[str] = set()
        for intent in intents:
            for phrase in INTENT_EXPANSIONS.get(intent, ()):
                intent_terms.update(self._content_terms(phrase))

        keep: list[RetrievedChunk] = []
        for chunk in chunks:
            section = str(chunk.metadata.get("section", "")).lower()
            body, triggers = self._split_searchable(chunk.text)
            haystack = f"{section} {body.lower()} {triggers.lower()}"

            if self._is_hard_excluded(section, haystack, intents):
                continue

            overlap_terms = {term for term in query_terms if self._term_in_text(term, haystack)}
            meaningful_overlap = {
                term for term in overlap_terms if term not in LOW_SIGNAL_TERMS and term not in STOPWORDS
            }
            intent_overlap = {term for term in intent_terms if self._term_in_text(term, haystack)}
            preferred = any(
                any(token in section for token in INTENT_SECTION_PREFERENCE.get(intent, ((), ()))[0])
                for intent in intents
            )

            if (
                meaningful_overlap
                or len(intent_overlap) >= 1
                or chunk.score >= 0.55
                or (preferred and chunk.score >= 0.32)
                or (not intents and chunk.score >= 0.4)
            ):
                keep.append(chunk)

        # Prefer section diversity, but allow a second chunk from a different
        # highly preferred section family for company/services intents.
        seen_sections: set[str] = set()
        final: list[RetrievedChunk] = []
        for chunk in sorted(keep, key=lambda item: item.score, reverse=True):
            section_key = str(chunk.metadata.get("section", chunk.id))
            if section_key in seen_sections:
                continue
            seen_sections.add(section_key)
            final.append(chunk)
            if len(final) >= self.settings.top_k:
                break
        return final

    def _soft_fallback(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        intents: list[str],
    ) -> list[RetrievedChunk]:
        kept: list[RetrievedChunk] = []
        for chunk in sorted(chunks, key=lambda item: item.score, reverse=True):
            section = str(chunk.metadata.get("section", "")).lower()
            body, triggers = self._split_searchable(chunk.text)
            haystack = f"{section} {body.lower()} {triggers.lower()}"
            if self._is_hard_excluded(section, haystack, intents):
                continue
            kept.append(chunk)
            if len(kept) >= min(3, self.settings.top_k):
                break
        return kept

    def _is_hard_excluded(self, section: str, haystack: str, intents: list[str]) -> bool:
        for intent in intents:
            _, avoid = INTENT_SECTION_PREFERENCE.get(intent, ((), ()))
            if any(token in section for token in avoid):
                evidence = INTENT_EXPANSIONS.get(intent, ())
                if not any(token.lower() in haystack for token in evidence[:5]):
                    return True

        if "travel_delight_guarantee" not in intents and (
            "terms & conditions" in section or "mission & guarantee" in section
        ):
            if any(intent in {"prm_assistance", "fast_track", "airport_coverage"} for intent in intents):
                return True

        if "pricing" in intents:
            pricing_evidence = (
                "price",
                "prices",
                "cost",
                "fee",
                "quote",
                "quotes",
                "rate",
                "rates",
                "discount",
                "avip@upgradevip.com",
                "whatsapp",
                "fixed rates",
                "contact",
            )
            coverage_only = "global availability" in section or "featured airports" in section
            if coverage_only and not any(token in haystack for token in pricing_evidence):
                return True
        return False

    def _section_intent_multiplier(self, section: str, intents: list[str]) -> float:
        if not intents:
            return 1.0
        section_l = section.lower()
        multiplier = 1.0
        for intent in intents:
            prefer, avoid = INTENT_SECTION_PREFERENCE.get(intent, ((), ()))
            if any(token in section_l for token in prefer):
                multiplier = max(multiplier, 1.35)
            if any(token in section_l for token in avoid):
                multiplier = min(multiplier, 0.4)
        return multiplier

    def _content_terms(self, text: str) -> list[str]:
        raw = [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2]
        terms = [token for token in raw if token not in STOPWORDS]
        seen: set[str] = set()
        ordered: list[str] = []
        for term in terms:
            if term not in seen:
                seen.add(term)
                ordered.append(term)
        return ordered

    def _term_in_text(self, term: str, text: str) -> bool:
        if term in text:
            return True
        for alias in TERM_ALIASES.get(term, ()):
            if alias in text:
                return True
        return False

    def _term_idf(self) -> dict[str, float]:
        if self._idf_cache is not None:
            return self._idf_cache

        doc_freq: Counter[str] = Counter()
        docs = self.vector_store.get_all()
        n_docs = max(len(docs), 1)
        for chunk in docs:
            body, triggers = self._split_searchable(chunk.text)
            terms = set(self._content_terms(f"{body} {triggers}"))
            terms.update(self._content_terms(str(chunk.metadata.get("section", ""))))
            for term in terms:
                doc_freq[term] += 1

        self._idf_cache = {
            term: math.log((1 + n_docs) / (1 + freq)) + 1.0
            for term, freq in doc_freq.items()
        }
        return self._idf_cache

    @staticmethod
    def _split_searchable(text: str) -> tuple[str, str]:
        """Return (body_without_triggers, trigger_phrases)."""
        triggers: list[str] = []
        for match in TRIGGER_LINE.finditer(text):
            triggers.append(match.group(1))
        body = TRIGGER_LINE.sub(" ", text)
        body = re.sub(r"\s+", " ", body).strip()
        trigger_text = " ".join(triggers)
        return body, trigger_text

    def _filter_chunks(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        seen: set[str] = set()
        filtered: list[RetrievedChunk] = []
        threshold = max(0.3, self.settings.similarity_threshold - 0.1)

        for chunk in sorted(chunks, key=lambda item: item.score, reverse=True):
            if chunk.score < threshold:
                continue
            dedupe_key = chunk.metadata.get("section", chunk.text[:120])
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            filtered.append(chunk)
        return filtered

    @staticmethod
    def build_context(chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return ""
        return "\n\n---\n\n".join(chunk.text for chunk in chunks)

    @staticmethod
    def to_sources(chunks: list[RetrievedChunk]) -> list[Source]:
        sources: list[Source] = []
        for chunk in chunks:
            sources.append(
                Source(
                    source=chunk.metadata.get("source", "unknown"),
                    section=chunk.metadata.get("section"),
                    metadata={
                        key: value
                        for key, value in chunk.metadata.items()
                        if key not in {"source", "section"}
                    },
                )
            )
        return sources
