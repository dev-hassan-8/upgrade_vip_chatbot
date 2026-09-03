from __future__ import annotations

import logging

from app.config import Settings, get_settings
from app.services.gemini_client import GeminiClient, get_gemini_client

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(
        self,
        settings: Settings | None = None,
        gemini_client: GeminiClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._gemini_client = gemini_client

    @property
    def gemini_client(self) -> GeminiClient:
        if self._gemini_client is None:
            self._gemini_client = get_gemini_client(self.settings)
        return self._gemini_client

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self.gemini_client.embed_texts(texts)

    def embed_query(self, query: str) -> list[float]:
        return self.embed_texts([query])[0]
