from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class OllamaResponse:
    response: str
    model: str | None = None
    created_at: str | None = None


class OllamaClient:
    """Tiny Ollama HTTP client.

    Uses the local Ollama REST API (/api/generate).
    """

    def __init__(self, base_url: str, *, timeout_seconds: int = 1800) -> None:
        timeout = httpx.Timeout(timeout_seconds, connect=10.0)
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        format: Any | None = None,
        options: dict[str, Any] | None = None,
    ) -> OllamaResponse:
        payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        if format is not None:
            payload["format"] = format
        if options:
            payload["options"] = options

        r = self._client.post("/api/generate", json=payload)
        r.raise_for_status()
        data = r.json()
        return OllamaResponse(
            response=str(data.get("response", "")),
            model=data.get("model"),
            created_at=data.get("created_at"),
        )

    @staticmethod
    def try_parse_json(text: str) -> dict[str, Any] | None:
        try:
            return json.loads(text)
        except Exception:
            return None
