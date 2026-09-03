from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from rag.config import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL, KNOWLEDGE_SOURCE
from rag.knowledge_loader import KnowledgeSection, load_knowledge_sections


class KnowledgeIndexer:
    def __init__(self, persist_dir: Path = CHROMA_DIR) -> None:
        self.persist_dir = persist_dir
        self.embedding_function = SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL
        )
        self.client = chromadb.PersistentClient(path=str(persist_dir))

    def build(self, source_path: Path = KNOWLEDGE_SOURCE) -> int:
        sections = load_knowledge_sections(source_path)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        try:
            self.client.delete_collection(COLLECTION_NAME)
        except ValueError:
            pass

        collection = self.client.create_collection(
            name=COLLECTION_NAME,
            embedding_function=self.embedding_function,
            metadata={"source": source_path.name},
        )

        collection.add(
            ids=[section.section_id for section in sections],
            documents=[section.embedding_text for section in sections],
            metadatas=[
                {
                    "title": section.title,
                    "source_file": section.source_file,
                    "triggers": ", ".join(section.triggers),
                    "content": section.content,
                }
                for section in sections
            ],
        )
        return len(sections)

    def get_collection(self):
        return self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self.embedding_function,
            metadata={"source": KNOWLEDGE_SOURCE.name},
        )

    @staticmethod
    def section_from_metadata(section_id: str, metadata: dict, distance: float | None) -> dict:
        return {
            "section_id": section_id,
            "title": metadata.get("title", ""),
            "triggers": metadata.get("triggers", ""),
            "content": metadata.get("content", ""),
            "source_file": metadata.get("source_file", KNOWLEDGE_SOURCE.name),
            "distance": distance,
        }
