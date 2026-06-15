"""Anthropic Claude HTTP client.

Mirrors the surface of OllamaClient (chat / chat_stream / aclose) so the
engine can use either without caring which one.

Uses raw httpx — no `anthropic` SDK dependency.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from .llm import ChatMessage


ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicError(RuntimeError):
    pass


class AnthropicClient:
    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
        timeout: float = 240.0,
        max_tokens: int = 2048,
    ) -> None:
        if not api_key:
            raise AnthropicError("Anthropic API key is empty")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    # ----- public API -----

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
        payload = self._build_payload(messages, temperature, top_p, stop, stream=False, max_tokens=max_tokens, model=model)
        try:
            resp = await self._client.post(
                ANTHROPIC_URL, json=payload, headers=self._headers(),
            )
            if resp.status_code >= 400:
                raise AnthropicError(
                    f"Anthropic HTTP {resp.status_code} (model={self.model!r}): "
                    f"{resp.text[:400]}"
                )
            data = resp.json()
        except httpx.HTTPError as exc:
            raise AnthropicError(
                f"Anthropic request failed ({type(exc).__name__}): {exc}"
            ) from exc

        blocks = data.get("content") or []
        text = "".join(
            b.get("text", "") for b in blocks if b.get("type") == "text"
        )
        if not text:
            raise AnthropicError(f"Empty Anthropic response: {data!r}")
        return text

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
        payload = self._build_payload(messages, temperature, top_p, stop, stream=True, max_tokens=max_tokens, model=model)
        try:
            async with self._client.stream(
                "POST", ANTHROPIC_URL, json=payload, headers=self._headers(),
            ) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")[:400]
                    raise AnthropicError(
                        f"Anthropic HTTP {resp.status_code} (model={self.model!r}): {body}"
                    )
                async for delta in _iter_sse_text(resp):
                    if delta:
                        yield delta
        except httpx.HTTPError as exc:
            raise AnthropicError(
                f"Anthropic stream failed ({type(exc).__name__}): {exc}"
            ) from exc

    # ----- internals -----

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

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
        # Anthropic은 system을 별도 필드로. 여러 개면 합침.
        sys_parts: list[str] = []
        msgs: list[dict] = []
        for m in messages:
            if m.role == "system":
                sys_parts.append(m.content)
            else:
                msgs.append({"role": m.role, "content": m.content})

        # 비어 있으면 사용자 메시지 하나 강제 (Anthropic은 user 필수)
        if not msgs:
            msgs = [{"role": "user", "content": "(빈 입력)"}]

        # Haiku 4.5 등 일부 모델은 temperature/top_p 동시 지정 불가 → temperature만 사용
        payload: dict = {
            "model": model or self.model,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "messages": msgs,
            "temperature": temperature,
            "stream": stream,
        }
        if sys_parts:
            payload["system"] = "\n\n".join(sys_parts)
        if stop:
            payload["stop_sequences"] = stop
        return payload


async def _iter_sse_text(resp) -> AsyncIterator[str]:
    """Anthropic SSE 파싱 — content_block_delta.text_delta 만 추출."""
    async for line in resp.aiter_lines():
        if not line or not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if not raw or raw == "[DONE]":
            continue
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "content_block_delta":
            delta = ev.get("delta") or {}
            if delta.get("type") == "text_delta":
                yield delta.get("text", "")
        elif ev.get("type") == "message_stop":
            return
