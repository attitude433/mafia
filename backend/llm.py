"""Ollama HTTP client wrapper.

Single async client used everywhere — game logic doesn't talk to Ollama
directly, it goes through OllamaClient.chat() / chat_stream().
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import AsyncIterator, Literal

import httpx

Role = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 600.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "gemma4:12b")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.8,
        top_p: float = 0.9,
        stop: list[str] | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> str:
        """Non-streaming chat completion. Returns the assistant text."""
        payload = self._build_payload(messages, temperature, top_p, stop, stream=False, max_tokens=max_tokens, model=model)
        if json_mode:
            payload["format"] = "json"
        try:
            resp = await self._client.post(f"{self.base_url}/api/chat", json=payload)
            if resp.status_code >= 400:
                raise OllamaError(
                    f"Ollama HTTP {resp.status_code} (model={self.model!r}): "
                    f"{resp.text[:300]}"
                )
            data = resp.json()
        except httpx.HTTPError as exc:
            raise OllamaError(
                f"Ollama request failed ({type(exc).__name__}, model={self.model!r}): {exc}"
            ) from exc

        message = data.get("message") or {}
        content = message.get("content", "")
        if not content:
            raise OllamaError(f"Empty response from Ollama: {data!r}")
        return content

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.8,
        top_p: float = 0.9,
        stop: list[str] | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        """Streaming chat completion. Yields content deltas."""
        payload = self._build_payload(messages, temperature, top_p, stop, stream=True, max_tokens=max_tokens, model=model)
        try:
            async with self._client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")[:300]
                    raise OllamaError(
                        f"Ollama HTTP {resp.status_code} (model={self.model!r}): {body}"
                    )
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = _safe_json(line)
                    if chunk is None:
                        continue
                    delta = (chunk.get("message") or {}).get("content")
                    if delta:
                        yield delta
                    if chunk.get("done"):
                        break
        except httpx.HTTPError as exc:
            raise OllamaError(
                f"Ollama stream failed ({type(exc).__name__}, model={self.model!r}): {exc}"
            ) from exc

    def _build_payload(
        self,
        messages: list[ChatMessage],
        temperature: float,
        top_p: float,
        stop: list[str] | None,
        *,
        stream: bool,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> dict:
        options: dict = {
            "temperature": temperature,
            "top_p": top_p,
            "num_ctx": 16384,
            "num_predict": max_tokens if max_tokens is not None else 2048,
        }
        if stop:
            options["stop"] = stop
        return {
            "model": model or self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": stream,
            "options": options,
            "keep_alive": -1,
        }


def _safe_json(line: str) -> dict | None:
    import json

    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None
