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
    "at", "for", "from", "with", "about", "into", "over", "after", "before", "between",
    "is", "are", "was", "were", "be", "been", "being", "am", "do", "does", "did", "doing",
    "can", "could", "would", "should", "will", "shall", "may", "might", "must",
    "i", "me", "my", "we", "our", "you", "your", "they", "them", "their", "it", "its",
    "this", "that", "these", "those", "there", "here", "what", "which", "who", "whom",
    "how", "when", "where", "why", "as", "by", "not", "no", "yes", "please", "thanks",
    "thank", "also", "just", "only", "very", "more", "most", "some", "any", "all",
    "every", "each", "other", "than", "too", "out", "up", "down", "off", "again",
    "further", "once", "have", "has", "had", "having", "get", "got", "make", "made",
}

# Generic words that appear across almost every UpgradeVIP section.
LOW_SIGNAL_TERMS = {
    "service", "services", "upgradevip", "upgrade", "vip", "company", "team",
    "customer", "clients", "client", "travel", "travelling", "traveling",
    "information", "details", "available", "offer", "offers", "provide", "provides",
    "provided", "help", "assist", "need", "needs", "want", "book", "booking",
}

INTENT_EXPANSIONS: dict[str, tuple[str, ...]] = {
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
    "company": (
        "brand philosophy",
        "mission",
        "partnerships",
        "fortune 500",
        "local operators",
    ),
    "contact": ("contact", "avip@upgradevip.com", "whatsapp", "offices"),
}

# Section substrings preferred / avoided per intent.
INTENT_SECTION_PREFERENCE: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # (prefer_substrings, avoid_substrings)
    "prm_assistance": (
        ("vip", "services", "who uses", "meet", "porter", "concierge"),
        ("terms & conditions", "travel delight", "privacy", "copyright", "social media"),
    ),
    "fast_track": (
        ("vip", "services", "meet", "global availability"),
        ("terms & conditions", "travel delight", "privacy", "copyright"),
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
        ("social media", "copyright", "brand philosophy"),
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
    "company": (
        ("about upgradevip", "mission", "experience", "partnerships", "brand"),
        ("social media", "copyright"),
    ),
    "contact": (("contact", "reach us"), ("copyright", "social media")),
}

TRIGGER_LINE = re.compile(r"(?im)^this section answers:.*$")
NO_RELEVANT_CONTEXT = "No relevant knowledge base context retrieved."
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
        )
        if any(keyword in normalized for keyword in factual_keywords):
            return True

        return len(normalized.split()) >= 4

    def detect_intents(self, query: str) -> list[str]:
        text = query.lower()
        intents: list[str] = []

        if any(k in text for k in ("price", "pricing", "cost", "how much", "discount", "fee", "quote")):
            intents.append("pricing")
        if any(k in text for k in ("wheelchair", "prm", "special assistance", "special-needs", "disability", "disabilities", "elderly passenger", "elderly passengers")):
            intents.append("prm_assistance")
        if "fast track" in text or "fast-track" in text or ("security" in text and "airport" in text):
            intents.append("fast_track")
        coverage_signals = any(
            k in text
            for k in (
                "terminal",
                "which airport",
                "operate at",
                "every airport",
                "at jfk",
                "at heathrow",
                "global",
                "where do you",
                "airports do you",
            )
        ) or (
            "airport" in text
            and any(k in text for k in ("vip", "service", "offer", "provide", "cover"))
            and "pricing" not in intents
            and not any(k in text for k in ("how much", "cost", "price", "discount"))
        )
        if coverage_signals:
            intents.append("airport_coverage")
        if any(k in text for k in ("transfer", "chauffeur", "pick me up", "drop off", "taxi")):
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
        if any(k in text for k in ("what can you book", "bot", "can i book", "can you book")):
            intents.append("booking_capabilities")
        if self._is_travel_delight_guarantee_query(text):
            intents.append("travel_delight_guarantee")
        if any(k in text for k in ("about upgradevip", "who are you", "company", "philosophy", "partnership", "since 2009")):
            intents.append("company")
        if any(k in text for k in ("contact", "email", "whatsapp", "phone", "office")):
            intents.append("contact")

        # De-dupe while preserving order
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
        # "Can you guarantee wheelchair/fast-track..." is operational, not the product guarantee.
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
        """Build multi-query variants for better lexical/semantic recall."""
        intents = self.detect_intents(query)
        variants = [query.strip()]
        for intent in intents:
            expansion = INTENT_EXPANSIONS.get(intent)
            if expansion:
                variants.append(f"{query} {' '.join(expansion)}")
        # Keep unique, stable order
        seen: set[str] = set()
        unique: list[str] = []
        for item in variants:
            key = item.lower()
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique[:4]

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        if self.vector_store.count() == 0:
            logger.warning("Vector store is empty during retrieval.")
            return []

        intents = self.detect_intents(query)
        variants = self.expand_queries(query)
        logger.info("Retrieval intents=%s variants=%s", intents, len(variants))

        keyword_hits = self._keyword_retrieve_multi(variants, intents)
        if keyword_hits:
            relevant = self._relevance_gate(query, keyword_hits, intents)
            if relevant:
                logger.info("Retrieved %s relevant chunks via keyword search", len(relevant))
                return relevant
            logger.info("Keyword hits rejected by relevance gate")

        # Embedding fallback only if store has embeddings.
        query_embedding = self.embedding_service.embed_query(variants[0])
        chunks = self.vector_store.query(
            query_embedding=query_embedding,
            top_k=max(self.settings.top_k * 3, 10),
        )
        filtered = self._filter_chunks(chunks)
        relevant = self._relevance_gate(query, filtered, intents)
        logger.info("Retrieved %s relevant chunks via embedding search", len(relevant))
        return relevant

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
        return ranked[: max(self.settings.top_k * 2, 8)]

    def _keyword_retrieve(self, query: str, intents: list[str]) -> list[RetrievedChunk]:
        terms = self._content_terms(query)
        if not terms:
            return []

        idf = self._term_idf()
        scored: list[RetrievedChunk] = []
        for chunk in self.vector_store.get_all():
            section = str(chunk.metadata.get("section", ""))
            body = self._searchable_text(chunk.text)
            haystack = f"{section} {body}".lower()

            weighted_matches = 0.0
            matched_content = 0
            for term in terms:
                if term in haystack:
                    weight = idf.get(term, 1.0)
                    if term in LOW_SIGNAL_TERMS:
                        weight *= 0.35
                    weighted_matches += weight
                    if term not in LOW_SIGNAL_TERMS:
                        matched_content += 1

            if weighted_matches <= 0:
                continue

            # Require at least one non-generic content term when the query has any.
            content_terms = [term for term in terms if term not in LOW_SIGNAL_TERMS]
            if content_terms and matched_content == 0:
                continue

            max_weight = sum(
                idf.get(term, 1.0) * (0.35 if term in LOW_SIGNAL_TERMS else 1.0)
                for term in terms
            ) or 1.0
            score = weighted_matches / max_weight
            score *= self._section_intent_multiplier(section, intents)

            # Strong exact phrase bonuses for precise topics.
            lowered_query = query.lower()
            if "wheelchair" in lowered_query and "wheelchair" not in haystack:
                # Wheelchair is not named in KB; allow PRM/special-assistance substitutes.
                if not any(token in haystack for token in ("special assistance", "prm", "elderly", "disabilities", "seniors")):
                    score *= 0.2
            if "travel delight" in lowered_query and "travel delight" in haystack:
                score = min(1.0, score + 0.35)
            if "private jet" in lowered_query and "private jet" in haystack:
                score = min(1.0, score + 0.25)
            if "hotel" in lowered_query and "hotel" in haystack:
                score = min(1.0, score + 0.25)

            chunk.score = score
            scored.append(chunk)

        scored.sort(key=lambda item: item.score, reverse=True)
        min_score = max(0.42, self.settings.similarity_threshold)
        strong = [chunk for chunk in scored if chunk.score >= min_score][: self.settings.top_k]
        return strong

    def _relevance_gate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        intents: list[str],
    ) -> list[RetrievedChunk]:
        """Drop cross-topic / weak matches before they reach the LLM."""
        if not chunks:
            return []

        query_terms = set(self._content_terms(query))
        intent_terms = set()
        for intent in intents:
            for phrase in INTENT_EXPANSIONS.get(intent, ()):
                intent_terms.update(self._content_terms(phrase))

        keep: list[RetrievedChunk] = []
        for chunk in chunks:
            section = str(chunk.metadata.get("section", "")).lower()
            body = self._searchable_text(chunk.text).lower()
            haystack = f"{section} {body}"

            # Hard avoid excluded sections for known intents.
            excluded = False
            for intent in intents:
                _, avoid = INTENT_SECTION_PREFERENCE.get(intent, ((), ()))
                if any(token in section for token in avoid):
                    # Allow if chunk still has strong intent-specific evidence.
                    evidence = INTENT_EXPANSIONS.get(intent, ())
                    if not any(token.lower() in haystack for token in evidence[:4]):
                        excluded = True
                        break
            if excluded:
                continue

            # Operational "guarantee X" must not use Travel Delight / T&Cs alone.
            if "travel_delight_guarantee" not in intents and (
                "terms & conditions" in section or "mission & guarantee" in section
            ):
                if any(intent in {"prm_assistance", "fast_track", "airport_coverage"} for intent in intents):
                    continue

            # Pricing questions should not be answered from pure coverage lists.
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
                    continue

            overlap_terms = {term for term in query_terms if term in haystack}
            meaningful_overlap = {
                term for term in overlap_terms if term not in LOW_SIGNAL_TERMS and term not in STOPWORDS
            }
            intent_overlap = {term for term in intent_terms if term in haystack}

            # Accept if meaningful lexical overlap OR solid intent evidence.
            if meaningful_overlap or len(intent_overlap) >= 2 or chunk.score >= 0.72:
                keep.append(chunk)
                continue

            # Weak generic-only overlap → reject.
            logger.debug(
                "Rejecting weak chunk %s score=%.3f overlap=%s",
                chunk.id,
                chunk.score,
                sorted(overlap_terms),
            )

        # Prefer diversity by section, keep top_k.
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

    def _section_intent_multiplier(self, section: str, intents: list[str]) -> float:
        if not intents:
            return 1.0
        section_l = section.lower()
        multiplier = 1.0
        for intent in intents:
            prefer, avoid = INTENT_SECTION_PREFERENCE.get(intent, ((), ()))
            if any(token in section_l for token in prefer):
                multiplier = max(multiplier, 1.25)
            if any(token in section_l for token in avoid):
                multiplier = min(multiplier, 0.45)
        return multiplier

    def _content_terms(self, text: str) -> list[str]:
        raw = [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2]
        terms = [token for token in raw if token not in STOPWORDS]
        # Preserve order, unique
        seen: set[str] = set()
        ordered: list[str] = []
        for term in terms:
            if term not in seen:
                seen.add(term)
                ordered.append(term)
        return ordered

    def _term_idf(self) -> dict[str, float]:
        if self._idf_cache is not None:
            return self._idf_cache

        doc_freq: Counter[str] = Counter()
        docs = self.vector_store.get_all()
        n_docs = max(len(docs), 1)
        for chunk in docs:
            terms = set(self._content_terms(self._searchable_text(chunk.text)))
            terms.update(self._content_terms(str(chunk.metadata.get("section", ""))))
            for term in terms:
                doc_freq[term] += 1

        self._idf_cache = {
            term: math.log((1 + n_docs) / (1 + freq)) + 1.0
            for term, freq in doc_freq.items()
        }
        return self._idf_cache

    @staticmethod
    def _searchable_text(text: str) -> str:
        """Down-weight noisy 'This section answers:' trigger spam for matching."""
        without_triggers = TRIGGER_LINE.sub(" ", text)
        return re.sub(r"\s+", " ", without_triggers).strip()

    def _filter_chunks(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        seen: set[str] = set()
        filtered: list[RetrievedChunk] = []
        threshold = max(self.settings.similarity_threshold, 0.42)

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
