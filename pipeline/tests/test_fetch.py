import httpx
import pytest

from vigie_pipeline.exceptions import FetchError
from vigie_pipeline.fetch import BoundedFetcher


def test_fetch_timeout_is_retried_and_structured() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("timeout", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(FetchError, match="2 tentative"):
        BoundedFetcher(client=client, attempts=2).fetch("https://example.com")
    assert attempts == 2


def test_fetch_rejects_oversized_or_wrong_content() -> None:
    oversized = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"content-type": "text/html"}, content=b"12345", request=request
            )
        )
    )
    with pytest.raises(FetchError, match=r"trop volumineux|Limite"):
        BoundedFetcher(client=oversized, max_bytes=4).fetch("https://example.com")

    wrong = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"content-type": "image/png"}, content=b"png", request=request
            )
        )
    )
    with pytest.raises(FetchError, match="Type de contenu"):
        BoundedFetcher(client=wrong).fetch("https://example.com")
