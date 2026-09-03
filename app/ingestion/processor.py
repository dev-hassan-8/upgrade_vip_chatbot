from __future__ import annotations

import logging
from pathlib import Path

from app.config import Settings, get_settings
from app.ingestion.chunker import TextChunk, chunk_document, stable_chunk_id
from app.ingestion.loader import discover_documents, load_document
from app.services.embedding_service import EmbeddingService
from app.services.gemini_errors import GeminiEmbeddingError
from app.vectorstore.base import VectorDocument
from app.vectorstore.chroma_store import ChromaVectorStore

logger = logging.getLogger(__name__)


class DocumentProcessor:
    def __init__(
        self,
        settings: Settings | None = None,
        vector_store: ChromaVectorStore | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.vector_store = vector_store or ChromaVectorStore(self.settings)
        self.embedding_service = embedding_service or EmbeddingService(self.settings)

    def ingest_directory(
        self,
        directory: Path | None = None,
        reset: bool = True,
    ) -> int:
        source_dir = directory or self.settings.knowledge_base_path
        documents = discover_documents(source_dir)
        if not documents:
            raise FileNotFoundError(f"No supported documents found in {source_dir}")

        logger.info("Loading documents...")
        logger.info("Loaded %s document(s).", len(documents))

        if reset:
            logger.info("Resetting ChromaDB collection: %s", self.settings.chroma_collection_name)
            self.vector_store.reset_collection()

        total_chunks = 0
        for path in documents:
            total_chunks += self.ingest_file(path, reset=False)
        return total_chunks

    def ingest_file(self, path: Path, reset: bool = False) -> int:
        if reset:
            self.vector_store.reset_collection()

        loaded = load_document(path)
        chunks = chunk_document(
            loaded,
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
        )
        logger.info("Created %s chunks from %s.", len(chunks), path.name)

        pending_chunks, skipped = self._filter_existing_chunks(chunks)
        if skipped:
            logger.info("Skipping %s chunks already present in ChromaDB.", skipped)

        if not pending_chunks:
            logger.info("No new chunks to embed for %s.", path.name)
            return 0

        logger.info("Embedding %s chunks with Gemini...", len(pending_chunks))
        try:
            vector_docs = self._chunks_to_vectors(pending_chunks)
        except GeminiEmbeddingError:
            raise
        except Exception as exc:
            logger.exception("Unexpected embedding failure")
            raise RuntimeError("Document embedding failed.") from exc

        self.vector_store.upsert_documents(vector_docs)
        logger.info("Stored %s vectors in ChromaDB.", len(vector_docs))
        return len(vector_docs)

    def ingest_upload(self, filename: str, content: bytes) -> int:
        temp_path = self.settings.knowledge_base_path / filename
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_bytes(content)
        return self.ingest_file(temp_path, reset=False)

    def _filter_existing_chunks(self, chunks: list[TextChunk]) -> tuple[list[TextChunk], int]:
        chunk_ids = [stable_chunk_id(chunk.source, chunk.chunk_index) for chunk in chunks]
        existing = self.vector_store.existing_ids(chunk_ids)
        pending = [
            chunk
            for chunk in chunks
            if stable_chunk_id(chunk.source, chunk.chunk_index) not in existing
        ]
        return pending, len(existing)

    def _chunks_to_vectors(self, chunks: list[TextChunk]) -> list[VectorDocument]:
        texts = [chunk.text for chunk in chunks]
        embeddings = self.embedding_service.embed_texts(texts)
        logger.info("Successfully embedded %s chunks.", len(embeddings))

        vector_docs: list[VectorDocument] = []
        for chunk, embedding in zip(chunks, embeddings):
            chunk_id = stable_chunk_id(chunk.source, chunk.chunk_index)
            metadata = {
                **chunk.metadata,
                "chunk_id": chunk_id,
                "embedding_model": self.settings.gemini_embedding_model,
            }
            vector_docs.append(
                VectorDocument(
                    id=chunk_id,
                    text=chunk.text,
                    embedding=embedding,
                    metadata=metadata,
                )
            )
        return vector_docs
