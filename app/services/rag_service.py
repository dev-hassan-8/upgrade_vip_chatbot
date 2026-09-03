from __future__ import annotations

from app.services.retrieval_service import RetrievalService
from app.vectorstore.base import RetrievedChunk


class RagService:
    def __init__(self, retrieval_service: RetrievalService | None = None) -> None:
        self.retrieval_service = retrieval_service or RetrievalService()

    def retrieve_context(self, query: str) -> tuple[str, list[RetrievedChunk]]:
        chunks = self.retrieval_service.retrieve(query)
        context = self.retrieval_service.build_context(chunks)
        return context, chunks
