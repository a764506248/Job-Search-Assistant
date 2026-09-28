import json
from typing import Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen


class EmbeddingUnavailableError(RuntimeError):
    pass


class Embedder(Protocol):
    model: str

    def health(self) -> dict[str, object]: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HttpEmbeddingClient:
    def __init__(self, base_url: str, model: str, timeout: float = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def health(self) -> dict[str, object]:
        return self._request("/health", None)

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = self._request("/embed", {"texts": texts})
        vectors = result.get("vectors")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbeddingUnavailableError("embedding service returned invalid vectors")
        return vectors  # type: ignore[return-value]

    def _request(self, path: str, payload: dict[str, object] | None) -> dict[str, object]:
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST" if body is not None else "GET",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                return json.loads(response.read())
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise EmbeddingUnavailableError(f"embedding service unavailable: {error}") from error
