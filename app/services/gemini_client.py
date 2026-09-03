from __future__ import annotations

import logging
import time

from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.config import Settings, get_settings
from app.services.gemini_errors import (
    GeminiEmbeddingError,
    classify_gemini_error,
)

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        self._client = genai.Client(api_key=self.settings.gemini_api_key)

    def generate(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        models = [
            self.settings.gemini_chat_model,
            self.settings.gemini_fallback_chat_model,
        ]
        models = [model for i, model in enumerate(models) if model and model not in models[:i]]
        last_error: RuntimeError | None = None

        for model in models:
            max_retries = self.settings.chat_max_retries
            for attempt in range(1, max_retries + 1):
                try:
                    response = self._client.models.generate_content(
                        model=model,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            temperature=temperature,
                            max_output_tokens=500,
                            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                                disable=True
                            ),
                        ),
                    )
                    return (response.text or "").strip()
                except APIError as exc:
                    info = classify_gemini_error(exc)
                    last_error = RuntimeError(info.user_message)
                    logger.warning(
                        "Gemini chat error model=%s attempt %s/%s kind=%s",
                        model,
                        attempt,
                        max_retries,
                        info.kind.value,
                    )
                    if info.retryable and attempt < max_retries:
                        wait_seconds = min(
                            info.retry_after_seconds or self.settings.chat_retry_delay,
                            self.settings.chat_retry_delay,
                        )
                        time.sleep(wait_seconds)
                        continue
                    break

        if last_error:
            raise last_error
        raise RuntimeError("Gemini chat request failed.")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        batch_size = self.settings.embedding_batch_size
        batch_delay = self.settings.embedding_batch_delay
        max_retries = self.settings.embedding_max_retries
        batches = [texts[index : index + batch_size] for index in range(0, len(texts), batch_size)]
        total_batches = len(batches)
        embeddings: list[list[float]] = []

        logger.info(
            "Embedding %s texts with Gemini in %s batches (batch size=%s).",
            len(texts),
            total_batches,
            batch_size,
        )

        for batch_number, batch in enumerate(batches, start=1):
            logger.info("Batch %s/%s (%s chunks)", batch_number, total_batches, len(batch))
            batch_embeddings = self._embed_batch_with_retry(
                batch=batch,
                batch_number=batch_number,
                max_retries=max_retries,
            )
            embeddings.extend(batch_embeddings)

            if batch_number < total_batches and batch_delay > 0:
                time.sleep(batch_delay)

        return embeddings

    def _embed_batch_with_retry(
        self,
        batch: list[str],
        batch_number: int,
        max_retries: int,
    ) -> list[list[float]]:
        last_error: GeminiEmbeddingError | None = None

        for attempt in range(1, max_retries + 1):
            try:
                response = self._client.models.embed_content(
                    model=self.settings.gemini_embedding_model,
                    contents=batch,
                )
                if not response.embeddings:
                    raise RuntimeError("Gemini returned no embeddings.")
                return [list(item.values) for item in response.embeddings]
            except APIError as exc:
                info = classify_gemini_error(exc)
                last_error = GeminiEmbeddingError(info)
                logger.warning(
                    "Gemini embedding batch %s failed attempt %s/%s kind=%s quota_metric=%s",
                    batch_number,
                    attempt,
                    max_retries,
                    info.kind.value,
                    info.quota_metric,
                )

                if not info.retryable or attempt >= max_retries:
                    logger.error("Gemini embedding error: %s", info.message)
                    raise last_error from exc

                wait_seconds = info.retry_after_seconds or (2**attempt)
                logger.warning(
                    "Rate limit detected. Retrying batch %s in %s seconds...",
                    batch_number,
                    wait_seconds,
                )
                time.sleep(wait_seconds)

        if last_error:
            raise last_error
        raise RuntimeError("Gemini embedding failed without a specific error.")


def get_gemini_client(settings: Settings | None = None) -> GeminiClient:
    return GeminiClient(settings)
