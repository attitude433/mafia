"""Persona system — auto-generation (LLM) and manual entry.

Personas are pure data (models.Persona). Roles are assigned separately by
the game setup; this module only deals with character sheets.
"""
from __future__ import annotations

import random
from typing import Awaitable, Callable

from .llm import ChatMessage, OllamaClient, OllamaError
from .models import Persona


_GEN_SYSTEM = (
    "너는 마피아 게임용 캐릭터 시트 생성기다. "
    "다음 형식으로 정확히 4줄만 출력. 다른 말 금지.\n"
    "이름: <성+이름 또는 인물명, 짧게>\n"
    "소개: <한 줄 자기소개 (나이/직업/성격 키워드)>\n"
    "말투: <반말/존대, 길이, 톤>\n"
    "습관: <말버릇·습관 1~2가지>"
)


def _parse_lines(raw: str) -> dict[str, str]:
    """줄 단위 'key: value' 파싱."""
    out: dict[str, str] = {}
    key_map = {"이름": "name", "소개": "summary", "말투": "style", "습관": "quirks"}
    for line in raw.splitlines():
        line = line.strip().lstrip("-•").strip()
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        if k in key_map:
            out[key_map[k]] = v.strip()
    return out


ProgressCb = Callable[[int, int, Persona], Awaitable[None]]


async def generate_one_persona(
    client: OllamaClient,
    *,
    theme: str | None = None,
    existing_names: list[str] | None = None,
) -> Persona:
    """단일 페르소나 1명을 LLM에 요청. 슬롯별 자동생성 버튼용."""
    used = set(existing_names or [])
    prev = ", ".join(used) or "없음"
    user_msg = (
        f"마피아 게임 참가자 1명의 페르소나를 만들어라.\n"
        f"이미 만든 인물: {prev}\n"
        f"겹치지 않게 다른 직업/성격/연령대로."
    )
    if theme:
        user_msg += f"\n분위기/배경: {theme}"

    raw = await client.chat(
        messages=[
            ChatMessage("system", _GEN_SYSTEM),
            ChatMessage("user", user_msg),
        ],
        temperature=1.0,
    )
    return _parse_single(raw, used)


async def generate_personas(
    client: OllamaClient,
    count: int,
    *,
    theme: str | None = None,
    progress: ProgressCb | None = None,
    partial: list[Persona] | None = None,
) -> list[Persona]:
    """LLM에게 페르소나를 한 명씩 N번 호출해 생성.

    실패하면 즉시 예외 전파 — 단, `partial` 리스트가 주어지면 그 리스트에
    부분 결과를 인플레이스로 누적하므로 호출자가 거기까지는 살릴 수 있다.
    `progress(i, total, persona)`로 한 명 완성 시마다 보고.
    """
    if count <= 0:
        return partial if partial is not None else []

    personas: list[Persona] = partial if partial is not None else []
    used_names: set[str] = {x.name for x in personas}

    for i in range(len(personas), count):
        prev = ", ".join(used_names) or "없음"
        user_msg = (
            f"마피아 게임 참가자 1명의 페르소나를 만들어라.\n"
            f"이미 만든 인물: {prev}\n"
            f"겹치지 않게 다른 직업/성격/연령대로."
        )
        if theme:
            user_msg += f"\n분위기/배경: {theme}"

        raw = await client.chat(
            messages=[
                ChatMessage("system", _GEN_SYSTEM),
                ChatMessage("user", user_msg),
            ],
            temperature=1.0,
        )

        p = _parse_single(raw, used_names)
        personas.append(p)
        used_names.add(p.name)

        if progress is not None:
            await progress(i + 1, count, p)

    return personas


def _parse_single(raw: str, used_names: set[str]) -> Persona:
    data = _parse_lines(raw)
    name = data.get("name", "").strip()
    if not name:
        raise ValueError(f"Persona parse failed (no name)\nraw={raw!r}")

    base = name
    j = 2
    while name in used_names:
        name = f"{base}{j}"
        j += 1

    return Persona(
        name=name,
        summary=data.get("summary", "").strip(),
        style=data.get("style", "").strip(),
        quirks=data.get("quirks", "").strip(),
    )


def manual_persona(
    name: str,
    summary: str = "",
    style: str = "",
    quirks: str = "",
) -> Persona:
    """GM이 직접 입력한 값으로 페르소나 구성. 검증만 거침."""
    name = name.strip()
    if not name:
        raise ValueError("Persona name is required")
    return Persona(
        name=name,
        summary=summary.strip(),
        style=style.strip(),
        quirks=quirks.strip(),
    )


# ---------- Fallback (Ollama 다운 / 파싱 실패 시) ----------

_FALLBACK_POOL: list[Persona] = [
    Persona(name="김상철", summary="50대 택시기사, 의심 많음", style="짧고 퉁명스러움", quirks="'아 글쎄' 입버릇"),
    Persona(name="박지수", summary="20대 대학원생, 차분함", style="존댓말, 조심스러움", quirks="말끝을 흐림"),
    Persona(name="이민호", summary="30대 회사원, 분석적", style="논리적·길게 설명", quirks="숫자를 자주 인용"),
    Persona(name="정혜린", summary="40대 카페 사장, 사교적", style="밝고 빠른 반말", quirks="웃음 섞어 말함"),
    Persona(name="최영수", summary="60대 은퇴 교사, 점잖음", style="존댓말, 천천히", quirks="옛이야기 자주 꺼냄"),
    Persona(name="한유진", summary="20대 유튜버, 직설적", style="반말, 짧음", quirks="비유를 즐겨씀"),
    Persona(name="윤도현", summary="30대 의사, 신중함", style="존댓말, 간결", quirks="단정적 결론 피함"),
    Persona(name="강나래", summary="40대 자영업자, 호탕함", style="반말, 큰 목소리 느낌", quirks="별명 잘 붙임"),
]


def fallback_personas(count: int) -> list[Persona]:
    """LLM 호출 실패 시 안전망. 풀에서 랜덤 추출."""
    if count <= 0:
        return []
    pool = list(_FALLBACK_POOL)
    random.shuffle(pool)
    while len(pool) < count:
        pool.extend(_FALLBACK_POOL)
    return [Persona(**p.model_dump()) for p in pool[:count]]
