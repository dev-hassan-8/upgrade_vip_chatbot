#!/usr/bin/env python3
"""Ingest documents from knowledge_base/ into persistent ChromaDB."""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from app.config import get_settings
from app.ingestion.processor import DocumentProcessor
from app.services.gemini_errors import GeminiEmbeddingError

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest UpgradeVIP knowledge documents.")
    parser.add_argument(
        "--file",
        type=str,
        help="Optional single file path to ingest instead of the whole knowledge_base directory.",
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Keep the existing collection and only embed/store missing chunks.",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.gemini_api_key:
        logger.error("GEMINI_API_KEY is not configured.")
        sys.exit(1)

    logger.info("Using Gemini embedding model: %s", settings.gemini_embedding_model)
    logger.info("Using ChromaDB collection: %s", settings.chroma_collection_name)

    processor = DocumentProcessor(settings)

    try:
        if args.file:
            path = Path(args.file)
            count = processor.ingest_file(path, reset=not args.no_reset)
        else:
            count = processor.ingest_directory(
                settings.knowledge_base_path,
                reset=not args.no_reset,
            )
    except GeminiEmbeddingError as exc:
        logger.error(exc.info.user_message)
        logger.error("Developer details: kind=%s status=%s", exc.info.kind, exc.info.status_code)
        sys.exit(1)
    except Exception as exc:
        logger.error("Ingestion failed: %s", exc)
        sys.exit(1)

    logger.info("Ingestion completed successfully. %s new chunk(s) stored.", count)


if __name__ == "__main__":
    main()
