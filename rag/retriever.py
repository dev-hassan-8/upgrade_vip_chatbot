from __future__ import annotations

import re

from rag.config import KNOWLEDGE_SOURCE, TOP_K
from rag.indexer import KnowledgeIndexer


class KnowledgeRetriever:
    def __init__(self, indexer: KnowledgeIndexer | None = None) -> None:
        self.indexer = indexer or KnowledgeIndexer()
        self.collection = self.indexer.get_collection()

    def retrieve(self, query: str, top_k: int = TOP_K) -> list[dict]:
        if self.collection.count() == 0:
            raise RuntimeError(
                "Knowledge index is empty. Run `python build_index.py` first."
            )

        semantic_results = self.collection.query(
            query_texts=[query],
            n_results=min(top_k, self.collection.count()),
            include=["metadatas", "distances"],
        )

        hits: dict[str, dict] = {}
        for section_id, metadata, distance in zip(
            semantic_results["ids"][0],
            semantic_results["metadatas"][0],
            semantic_results["distances"][0],
        ):
            hit = self.indexer.section_from_metadata(section_id, metadata, distance)
            hit["keyword_score"] = self._keyword_score(query, metadata.get("triggers", ""))
            hit["score"] = hit["keyword_score"] - (distance or 0.0)
            hits[section_id] = hit

        keyword_hits = self._keyword_search(query, top_k=top_k)
        for hit in keyword_hits:
            existing = hits.get(hit["section_id"])
            if existing:
                existing["keyword_score"] = max(
                    existing["keyword_score"], hit["keyword_score"]
                )
                existing["score"] = existing["keyword_score"] - (
                    existing["distance"] or 0.0
                )
            else:
                hits[hit["section_id"]] = hit

        ranked = sorted(hits.values(), key=lambda item: item["score"], reverse=True)
        return ranked[:top_k]

    def _keyword_search(self, query: str, top_k: int) -> list[dict]:
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        all_sections = self.collection.get(include=["metadatas"])
        scored: list[dict] = []

        for section_id, metadata in zip(all_sections["ids"], all_sections["metadatas"]):
            triggers = metadata.get("triggers", "")
            title = metadata.get("title", "")
            content = metadata.get("content", "")
            keyword_score = self._keyword_score(
                query,
                f"{title} {triggers} {content}",
            )
            if keyword_score <= 0:
                continue

            hit = self.indexer.section_from_metadata(section_id, metadata, None)
            hit["keyword_score"] = keyword_score
            hit["score"] = keyword_score
            scored.append(hit)

        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]+", text.lower())
            if len(token) > 2
        }

    @classmethod
    def _keyword_score(cls, query: str, searchable_text: str) -> float:
        query_terms = cls._tokenize(query)
        if not query_terms:
            return 0.0

        haystack = searchable_text.lower()
        matches = sum(1 for term in query_terms if term in haystack)
        return matches / len(query_terms)

    @staticmethod
    def format_context(chunks: list[dict]) -> str:
        if not chunks:
            return ""

        parts: list[str] = []
        for chunk in chunks:
            title = chunk.get("title", "Unknown section")
            content = chunk.get("content", "")
            parts.append(f"=== {title} ===\n{content}")
        return "\n\n---\n\n".join(parts)
