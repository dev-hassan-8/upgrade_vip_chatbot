from app.services.gemini_errors import GeminiErrorKind, classify_gemini_error


def test_classify_rate_limit_with_retry_after() -> None:
    error = Exception(
        "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, "
        "'message': 'Please retry in 4.5s.', 'details': ["
        "{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '4s'}"
        "]}}"
    )
    info = classify_gemini_error(error)
    assert info.kind == GeminiErrorKind.RATE_LIMIT
    assert info.retry_after_seconds == 4.5 or info.retry_after_seconds == 4.0


def test_classify_daily_quota_exhausted() -> None:
    error = Exception(
        "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'details': ["
        "{'quotaMetric': 'generativelanguage.googleapis.com/embed_content_free_tier_requests', "
        "'quotaId': 'EmbedContentRequestsPerDayPerProjectPerModel-FreeTier'}"
        "]}}"
    )
    info = classify_gemini_error(error)
    assert info.kind == GeminiErrorKind.QUOTA_EXHAUSTED


def test_classify_invalid_api_key() -> None:
    error = Exception("403 PERMISSION_DENIED API key not valid.")
    info = classify_gemini_error(error)
    assert info.kind == GeminiErrorKind.INVALID_API_KEY
