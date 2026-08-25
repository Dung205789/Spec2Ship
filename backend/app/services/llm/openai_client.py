from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI


@dataclass(frozen=True)
class OpenAIResponse:
    response: str
    model: str | None = None


class OpenAIClient:
    """Tiny OpenAI chat-completions client, shaped like OllamaClient.

    Kept as a thin wrapper (rather than calling the SDK directly from
    patches.py) so OpenAIWorkspacePatcher mirrors OllamaWorkspacePatcher's
    call shape and the two are easy to compare side by side.
    """

    def __init__(self, api_key: str, *, timeout_seconds: int = 120) -> None:
        self._client = OpenAI(api_key=api_key, timeout=timeout_seconds)

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        json_mode: bool = True,
        options: dict[str, Any] | None = None,
    ) -> OpenAIResponse:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {"model": model, "messages": messages}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if options:
            if "temperature" in options:
                kwargs["temperature"] = options["temperature"]

        resp = self._client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content or ""
        return OpenAIResponse(response=text, model=resp.model)

    @staticmethod
    def try_parse_json(text: str) -> dict[str, Any] | None:
        try:
            return json.loads(text)
        except Exception:
            return None
