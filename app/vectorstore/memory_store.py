from __future__ import annotations

from app.config import Settings, get_settings
from app.ingestion.chunker import chunk_document, stable_chunk_id
from app.ingestion.loader import discover_documents, load_document
from app.vectorstore.base import RetrievedChunk, VectorDocument, VectorStore


class KnowledgeMemoryStore(VectorStore):
    """In-memory chunks from the knowledge base. Safe on read-only serverless disks."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._documents: dict[str, VectorDocument] = {}
        self._load_knowledge_base()

    def _load_knowledge_base(self) -> None:
        source_dir = self.settings.knowledge_base_path
        for path in discover_documents(source_dir):
            loaded = load_document(path)
            chunks = chunk_document(
                loaded,
                chunk_size=self.settings.chunk_size,
                chunk_overlap=self.settings.chunk_overlap,
            )
            for chunk in chunks:
                chunk_id = stable_chunk_id(chunk.source, chunk.chunk_index)
                self._documents[chunk_id] = VectorDocument(
                    id=chunk_id,
                    text=chunk.text,
                    embedding=None,
                    metadata={
                        **chunk.metadata,
                        "chunk_id": chunk_id,
                    },
                )

    def reset_collection(self) -> None:
        self._documents.clear()

    def existing_ids(self, ids: list[str]) -> set[str]:
        return {item_id for item_id in ids if item_id in self._documents}

    def upsert_documents(self, documents: list[VectorDocument]) -> None:
        for document in documents:
            self._documents[document.id] = document

    def add_documents(self, documents: list[VectorDocument]) -> None:
        self.upsert_documents(documents)

    def query(
        self,
        query_embedding: list[float],
        top_k: int,
    ) -> list[RetrievedChunk]:
        scored: list[RetrievedChunk] = []
        for document in self._documents.values():
            if not document.embedding:
                continue
            score = _cosine_similarity(query_embedding, document.embedding)
            scored.append(
                RetrievedChunk(
                    id=document.id,
                    text=document.text,
                    metadata=document.metadata,
                    score=score,
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]

    def get_all(self) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                id=document.id,
                text=document.text,
                metadata=document.metadata,
                score=0.0,
            )
            for document in self._documents.values()
        ]

    def count(self) -> int:
        return len(self._documents)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
