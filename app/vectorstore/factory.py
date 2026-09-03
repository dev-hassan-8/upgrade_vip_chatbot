from __future__ import annotations

from app.config import Settings, get_settings
from app.vectorstore.base import VectorStore
from app.vectorstore.memory_store import KnowledgeMemoryStore


def get_vector_store(settings: Settings | None = None) -> VectorStore:
    settings = settings or get_settings()
    if settings.use_memory_vector_store:
        return KnowledgeMemoryStore(settings)

    try:
        from app.vectorstore.chroma_store import ChromaVectorStore

        return ChromaVectorStore(settings)
    except Exception:
        return KnowledgeMemoryStore(settings)
