from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class GeminiErrorKind(str, Enum):
    RATE_LIMIT = "rate_limit"
    QUOTA_EXHAUSTED = "quota_exhausted"
    TEMPORARY_UNAVAILABLE = "temporary_unavailable"
    INVALID_API_KEY = "invalid_api_key"
    OTHER = "other"


@dataclass
class GeminiErrorInfo:
    kind: GeminiErrorKind
    status_code: int
    message: str
    retry_after_seconds: float | None = None
    quota_metric: str | None = None

    @property
    def retryable(self) -> bool:
        return self.kind in {
            GeminiErrorKind.RATE_LIMIT,
            GeminiErrorKind.TEMPORARY_UNAVAILABLE,
        }

    @property
    def user_message(self) -> str:
        if self.kind == GeminiErrorKind.INVALID_API_KEY:
            return "Gemini API key is invalid or not authorised."
        if self.kind == GeminiErrorKind.QUOTA_EXHAUSTED:
            return (
                "Gemini quota has been reached. "
                "Please wait for the quota to reset or check billing settings."
            )
        if self.kind == GeminiErrorKind.TEMPORARY_UNAVAILABLE:
            return (
                "The assistant is busy at the moment. Please try again in a few seconds."
            )
        if self.kind == GeminiErrorKind.RATE_LIMIT:
            return "Too many requests right now. Please try again shortly."
        return "Gemini API request failed."


class GeminiEmbeddingError(RuntimeError):
    def __init__(self, info: GeminiErrorInfo) -> None:
        super().__init__(info.user_message)
        self.info = info


def classify_gemini_error(exc: Exception) -> GeminiErrorInfo:
    status_code = getattr(exc, "code", None) or _extract_status_code(str(exc))
    message = str(exc)
    lower_message = message.lower()

    retry_after = _extract_retry_after(exc, message)
    quota_metric = _extract_quota_metric(message)

    if status_code in {401, 403} or "api key" in lower_message and "invalid" in lower_message:
        return GeminiErrorInfo(
            kind=GeminiErrorKind.INVALID_API_KEY,
            status_code=status_code or 403,
            message=message,
        )

    if status_code == 429:
        quota_id = _extract_quota_id(message)
        if (quota_metric and "perday" in quota_metric.lower()) or (
            quota_id and "perday" in quota_id.lower()
        ):
            logger.error(
                "Gemini daily quota exhausted. metric=%s message=%s",
                quota_metric,
                message,
            )
            return GeminiErrorInfo(
                kind=GeminiErrorKind.QUOTA_EXHAUSTED,
                status_code=429,
                message=message,
                retry_after_seconds=retry_after,
                quota_metric=quota_metric,
            )

        logger.warning(
            "Gemini rate limit detected. retry_after=%s message=%s",
            retry_after,
            message,
        )
        return GeminiErrorInfo(
            kind=GeminiErrorKind.RATE_LIMIT,
            status_code=429,
            message=message,
            retry_after_seconds=retry_after,
            quota_metric=quota_metric,
        )

    if status_code in {503, 500} or "high demand" in lower_message or "unavailable" in lower_message:
        logger.warning("Gemini temporarily unavailable. message=%s", message)
        return GeminiErrorInfo(
            kind=GeminiErrorKind.TEMPORARY_UNAVAILABLE,
            status_code=status_code or 503,
            message=message,
            retry_after_seconds=retry_after or 2.0,
        )

    return GeminiErrorInfo(
        kind=GeminiErrorKind.OTHER,
        status_code=status_code or 500,
        message=message,
        retry_after_seconds=retry_after,
        quota_metric=quota_metric,
    )


def _extract_status_code(text: str) -> int | None:
    match = re.search(r"\b(4\d{2}|5\d{2})\b", text)
    return int(match.group(1)) if match else None


def _extract_retry_after(exc: Exception, message: str) -> float | None:
    response = getattr(exc, "response", None)
    if response is not None:
        retry_after_header = getattr(response, "headers", {}).get("Retry-After")
        if retry_after_header:
            try:
                return float(retry_after_header)
            except ValueError:
                pass

    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        retry_delay = details.get("retryDelay") or details.get("retry_delay")
        if retry_delay:
            return _parse_delay_seconds(str(retry_delay))

    match = re.search(r"retry in ([0-9.]+)s", message, re.IGNORECASE)
    if match:
        return float(match.group(1))

    match = re.search(r"'retryDelay': '([0-9.]+)s'", message)
    if match:
        return float(match.group(1))

    return None


def _extract_quota_metric(message: str) -> str | None:
    match = re.search(r"'quotaMetric': '([^']+)'", message)
    if match:
        return match.group(1)
    match = re.search(r'"quotaMetric": "([^"]+)"', message)
    return match.group(1) if match else None


def _extract_quota_id(message: str) -> str | None:
    match = re.search(r"'quotaId': '([^']+)'", message)
    if match:
        return match.group(1)
    match = re.search(r'"quotaId": "([^"]+)"', message)
    return match.group(1) if match else None


def _parse_delay_seconds(value: str) -> float:
    value = value.strip().lower()
    if value.endswith("s"):
        return float(value[:-1])
    return float(value)
