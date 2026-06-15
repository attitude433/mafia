"""Game data models — enums + Pydantic types.

These are the pure data shapes. Runtime mutation lives in `game.py`.
Anything serialized over WebSocket goes through these.
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------- Enums ----------

class Role(str, Enum):
    MAFIA = "mafia"
    POLICE = "police"
    DOCTOR = "doctor"
    MEDIUM = "medium"
    CITIZEN = "citizen"


class Phase(str, Enum):
    SETUP = "setup"
    DAY_DISCUSSION = "day_discussion"
    DAY_VOTING = "day_voting"
    NIGHT = "night"
    ENDED = "ended"


class ChannelKind(str, Enum):
    PUBLIC = "public"          # 낮 전체 공개
    MAFIA = "mafia"            # 마피아 단톡 + GM
    PRIVATE = "private"        # 능력자 1:1 GM (경찰/의사 등)
    MEDIUM = "medium"          # 영매 ↔ 죽은 유닛 + GM


SpeakerKind = Literal["unit", "gm", "system"]


# ---------- Core models ----------

class Persona(BaseModel):
    """유닛의 성격 시트. 시스템 프롬프트에 박힌다."""
    name: str
    summary: str            # 한 줄 자기소개 ("40대 경비원, 무뚝뚝함")
    style: str = ""         # 말투/어조 ("짧고 단호하게 말함")
    quirks: str = ""        # 기벽/습관 ("말끝마다 '글쎄...'")


class NightState(BaseModel):
    """밤마다 리셋되는 유닛별 상태."""
    targeted_by_mafia: bool = False
    protected_by_doctor: bool = False
    investigated_by_police: bool = False


class Unit(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    persona: Persona
    role: Role
    model: str = ""        # 유닛 전용 LLM 모델 (예: 'gemma3:4b'). 비우면 엔진 기본
    alive: bool = True
    night: NightState = Field(default_factory=NightState)

    @property
    def name(self) -> str:
        return self.persona.name


class ChatLine(BaseModel):
    channel_id: str
    speaker_kind: SpeakerKind
    speaker_id: str          # unit.id, "gm", or "system"
    speaker_name: str
    content: str
    ts: float = Field(default_factory=time.time)


class Channel(BaseModel):
    id: str
    kind: ChannelKind
    label: str               # GM에게 보일 이름 ("공개 채팅", "마피아 단톡", "경찰 - 김씨")
    member_ids: list[str]    # 이 채널을 볼 수 있는 unit.id 목록 (GM은 항상 포함되는 것으로 간주)


class Vote(BaseModel):
    voter_id: str
    target_id: str | None    # None = 기권/파싱 실패
    raw: str                 # 원 발언


# ---------- Snapshot (for sending to frontend) ----------

class GameSnapshot(BaseModel):
    phase: Phase
    day: int
    units: list[Unit]
    channels: list[Channel]
    active_channel_id: str | None
    speaking_unit_id: str | None
    votes: list[Vote] = []
