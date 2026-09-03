#!/usr/bin/env python3
"""Build the UpgradeVIP knowledge index from upgradevip_details.txt."""

from rag.config import KNOWLEDGE_SOURCE
from rag.indexer import KnowledgeIndexer


def main() -> None:
    print(f"Building index from: {KNOWLEDGE_SOURCE}")
    indexer = KnowledgeIndexer()
    section_count = indexer.build(KNOWLEDGE_SOURCE)
    print(f"Indexed {section_count} sections into the RAG knowledge store.")


if __name__ == "__main__":
    main()
