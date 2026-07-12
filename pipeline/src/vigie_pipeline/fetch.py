"""Client HTTP borné avec reprises et contrôle du type et de la taille."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from vigie_pipeline.exceptions import FetchError

ALLOWED_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "application/pdf",
    "application/json",
    "text/plain",
    "application/octet-stream",
}


@dataclass(frozen=True)
class FetchResult:
    url: str
    content: bytes
    content_type: str
    etag: str | None
    last_modified: str | None


class BoundedFetcher:
    """Récupère uniquement des réponses bornées et explicitement autorisées."""

    def __init__(
        self,
        *,
        timeout: float = 20,
        attempts: int = 3,
        max_bytes: int = 15_000_000,
        client: httpx.Client | None = None,
    ) -> None:
        self.attempts = attempts
        self.max_bytes = max_bytes
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            max_redirects=5,
            headers={
                "User-Agent": "VigieIndustrieBot/2.0 (+https://github.com/jeplante/vigie_industrie)"
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> BoundedFetcher:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch(self, url: str, allowed_types: Iterable[str] = ALLOWED_CONTENT_TYPES) -> FetchResult:
        allowed = set(allowed_types)

        @retry(
            stop=stop_after_attempt(self.attempts),
            wait=wait_exponential(multiplier=0.2, min=0.2, max=2),
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
            reraise=True,
        )
        def request() -> FetchResult:
            try:
                with self.client.stream("GET", url) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if content_type not in allowed:
                        raise FetchError(
                            f"Type de contenu refusé pour {url}: {content_type or 'absent'}"
                        )
                    declared = int(response.headers.get("content-length", "0") or 0)
                    if declared > self.max_bytes:
                        raise FetchError(f"Contenu trop volumineux pour {url}: {declared} octets")
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise FetchError(
                                f"Limite de {self.max_bytes} octets dépassée pour {url}"
                            )
                        chunks.append(chunk)
                    return FetchResult(
                        url=str(response.url),
                        content=b"".join(chunks),
                        content_type=content_type,
                        etag=response.headers.get("etag"),
                        last_modified=response.headers.get("last-modified"),
                    )
            except httpx.HTTPStatusError as error:
                raise FetchError(f"Erreur HTTP {error.response.status_code} pour {url}") from error
            except (httpx.TimeoutException, httpx.NetworkError):
                raise
            except httpx.HTTPError as error:
                raise FetchError(f"Erreur HTTP pour {url}: {error.__class__.__name__}") from error

        try:
            return request()
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise FetchError(
                f"Source inaccessible après {self.attempts} tentative(s): {url}"
            ) from error
