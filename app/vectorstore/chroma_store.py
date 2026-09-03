from __future__ import annotations

from app.config import Settings, get_settings
from app.vectorstore.base import RetrievedChunk, VectorDocument, VectorStore


class ChromaVectorStore(VectorStore):
    def __init__(self, settings: Settings | None = None) -> None:
        import chromadb

        self.settings = settings or get_settings()
        self.persist_dir = self.settings.chroma_path
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self.client.get_or_create_collection(
            name=self.settings.chroma_collection_name,
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": self.settings.gemini_embedding_model,
                "provider": "gemini",
            },
        )

    def reset_collection(self) -> None:
        try:
            self.client.delete_collection(self.settings.chroma_collection_name)
        except ValueError:
            pass
        self.collection = self.client.create_collection(
            name=self.settings.chroma_collection_name,
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": self.settings.gemini_embedding_model,
                "provider": "gemini",
            },
        )

    def existing_ids(self, ids: list[str]) -> set[str]:
        if not ids or self.count() == 0:
            return set()
        result = self.collection.get(ids=ids, include=[])
        return set(result.get("ids") or [])

    def upsert_documents(self, documents: list[VectorDocument]) -> None:
        if not documents:
            return

        self.collection.upsert(
            ids=[doc.id for doc in documents],
            documents=[doc.text for doc in documents],
            embeddings=[doc.embedding for doc in documents],
            metadatas=[doc.metadata for doc in documents],
        )

    def add_documents(self, documents: list[VectorDocument]) -> None:
        self.upsert_documents(documents)

    def query(
        self,
        query_embedding: list[float],
        top_k: int,
    ) -> list[RetrievedChunk]:
        if self.count() == 0:
            return []

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.count()),
            include=["documents", "metadatas", "distances"],
        )

        chunks: list[RetrievedChunk] = []
        for doc_id, text, metadata, distance in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            score = 1.0 - float(distance)
            chunks.append(
                RetrievedChunk(
                    id=doc_id,
                    text=text,
                    metadata=metadata or {},
                    score=score,
                )
            )
        return chunks

    def get_all(self) -> list[RetrievedChunk]:
        if self.count() == 0:
            return []
        results = self.collection.get(include=["documents", "metadatas"])
        chunks: list[RetrievedChunk] = []
        for doc_id, text, metadata in zip(
            results.get("ids") or [],
            results.get("documents") or [],
            results.get("metadatas") or [],
        ):
            chunks.append(
                RetrievedChunk(
                    id=doc_id,
                    text=text or "",
                    metadata=metadata or {},
                    score=0.0,
                )
            )
        return chunks

    def count(self) -> int:
        return self.collection.count()
