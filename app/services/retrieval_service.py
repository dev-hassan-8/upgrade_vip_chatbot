from __future__ import annotations

import logging
import re

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

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        if self.vector_store.count() == 0:
            logger.warning("Vector store is empty during retrieval.")
            return []

        keyword_hits = self._keyword_retrieve(query)
        if keyword_hits:
            logger.info("Retrieved %s chunks via keyword search", len(keyword_hits))
            return keyword_hits

        query_embedding = self.embedding_service.embed_query(query)
        chunks = self.vector_store.query(
            query_embedding=query_embedding,
            top_k=self.settings.top_k,
        )
        filtered = self._filter_chunks(chunks)
        logger.info("Retrieved %s chunks via embedding search", len(filtered))
        return filtered

    def _keyword_retrieve(self, query: str) -> list[RetrievedChunk]:
        terms = {
            token
            for token in re.findall(r"[a-z0-9]+", query.lower())
            if len(token) > 2
        }
        if not terms:
            return []

        scored: list[RetrievedChunk] = []
        for chunk in self.vector_store.get_all():
            haystack = f"{chunk.metadata.get('section', '')} {chunk.text}".lower()
            matches = sum(1 for term in terms if term in haystack)
            if matches == 0:
                continue
            chunk.score = matches / len(terms)
            scored.append(chunk)

        scored.sort(key=lambda item: item.score, reverse=True)
        strong = [chunk for chunk in scored if chunk.score >= 0.25][: self.settings.top_k]
        return strong

    def _filter_chunks(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        seen: set[str] = set()
        filtered: list[RetrievedChunk] = []

        for chunk in sorted(chunks, key=lambda item: item.score, reverse=True):
            if chunk.score < self.settings.similarity_threshold:
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
