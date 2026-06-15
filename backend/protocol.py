"""WebSocket message protocol — incoming (GM → server) and outgoing.

Incoming messages are a discriminated union by `type`. The engine dispatches
on that field. Outgoing messages are plain dicts so we can stream partial
LLM deltas without ceremony.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter


# ---------- Incoming ----------

class _InBase(BaseModel):
    type: str


class SetupMsg(_InBase):
    type: Literal["setup"] = "setup"
    persona_mode: Literal["auto", "manual"]
    count: int
    role_config: dict[str, int]
    personas: list[dict[str, str]] = []   # manual 모드에서만 사용
    theme: str | None = None
    system_prompt: str | None = None      # 모든 유닛 공통 프리픽스
    provider: Literal["anthropic", "ollama"] = "anthropic"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5-20251001"
    ollama_model: str | None = None


class ConfigProviderMsg(_InBase):
    """셋업 전에 자동생성 등으로 LLM이 필요할 때 사용."""
    type: Literal["config_provider"] = "config_provider"
    provider: Literal["anthropic", "ollama"]
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5-20251001"
    ollama_model: str | None = None


class GenOnePersonaMsg(_InBase):
    """슬롯 한 칸에 대해 LLM 자동 생성 1회."""
    type: Literal["gen_one_persona"] = "gen_one_persona"
    slot_id: int
    existing_names: list[str] = []
    theme: str | None = None


class StartDayMsg(_InBase):
    type: Literal["start_day"] = "start_day"


class StartVotingMsg(_InBase):
    type: Literal["start_voting"] = "start_voting"


class StartNightMsg(_InBase):
    type: Literal["start_night"] = "start_night"


class NextSpeakerMsg(_InBase):
    """GM이 라운드 로빈을 한 칸 진행."""
    type: Literal["next_speaker"] = "next_speaker"


class GMSayMsg(_InBase):
    """GM이 특정 채널에 직접 발언."""
    type: Literal["gm_say"] = "gm_say"
    channel_id: str
    content: str


class SetActiveChannelMsg(_InBase):
    type: Literal["set_active_channel"] = "set_active_channel"
    channel_id: str


class KillUnitMsg(_InBase):
    type: Literal["kill_unit"] = "kill_unit"
    unit_id: str


class SetNightFlagMsg(_InBase):
    """유닛 상태 패널 버튼 토글."""
    type: Literal["set_night_flag"] = "set_night_flag"
    unit_id: str
    flag: Literal["targeted_by_mafia", "protected_by_doctor", "investigated_by_police"]
    value: bool


class ApplyNightMsg(_InBase):
    """밤 결과 해소: 타겟 - 보호 = 사망 처리."""
    type: Literal["apply_night"] = "apply_night"


class SummonDeadMsg(_InBase):
    """영매가 죽은 유닛을 호출 — 해당 죽은 자를 medium 채널에 임시 멤버로 추가."""
    type: Literal["summon_dead"] = "summon_dead"
    medium_channel_id: str
    dead_unit_id: str


class SpeakInChannelMsg(_InBase):
    """밤 페이즈: 특정 유닛이 특정 채널에서 발언."""
    type: Literal["speak_in_channel"] = "speak_in_channel"
    unit_id: str
    channel_id: str


class SpeakDeadMsg(_InBase):
    """영매 채널에서 죽은 유닛이 발언."""
    type: Literal["speak_dead"] = "speak_dead"
    dead_unit_id: str
    medium_channel_id: str


class FinalDefenseMsg(_InBase):
    """최다 득표자가 최후의 변론을 한다."""
    type: Literal["final_defense"] = "final_defense"
    unit_id: str | None = None    # 미지정 시 현재 최다 득표자


class AIVoteMsg(_InBase):
    """살아있는 AI 전원이 구조화된 이름만 출력하는 투표 라운드."""
    type: Literal["ai_vote"] = "ai_vote"
    reset: bool = True    # 기존 표 초기화 후 시작


class ApprovalVoteMsg(_InBase):
    """최후의 변론 직후 찬성/반대 투표. defendant_id 미지정 시 최다 득표자."""
    type: Literal["approval_vote"] = "approval_vote"
    defendant_id: str | None = None


class MafiaTargetVoteMsg(_InBase):
    """살아있는 마피아 전원이 한 표씩 표적을 지목. 최다 득표자 자동 표적화."""
    type: Literal["mafia_target_vote"] = "mafia_target_vote"
    auto_apply: bool = True   # 결과를 targeted_by_mafia 플래그에 자동 반영


class MafiaDeliberateMsg(_InBase):
    """마피아끼리 표적이 합의될 때까지 무한 토론 (안전 한계 있음)."""
    type: Literal["mafia_deliberate"] = "mafia_deliberate"
    max_speeches: int = 20


class StopDeliberationMsg(_InBase):
    """진행 중인 무한 토론 중단."""
    type: Literal["stop_deliberation"] = "stop_deliberation"


class EndGameMsg(_InBase):
    type: Literal["end_game"] = "end_game"


class RequestSnapshotMsg(_InBase):
    type: Literal["request_snapshot"] = "request_snapshot"


InMessage = Annotated[
    Union[
        SetupMsg,
        StartDayMsg,
        StartVotingMsg,
        StartNightMsg,
        NextSpeakerMsg,
        GMSayMsg,
        SetActiveChannelMsg,
        KillUnitMsg,
        SetNightFlagMsg,
        ApplyNightMsg,
        SummonDeadMsg,
        SpeakInChannelMsg,
        SpeakDeadMsg,
        FinalDefenseMsg,
        AIVoteMsg,
        ApprovalVoteMsg,
        MafiaTargetVoteMsg,
        MafiaDeliberateMsg,
        StopDeliberationMsg,
        EndGameMsg,
        RequestSnapshotMsg,
        GenOnePersonaMsg,
        ConfigProviderMsg,
    ],
    Field(discriminator="type"),
]


_in_adapter = TypeAdapter(InMessage)


def parse_in(raw: dict[str, Any]) -> InMessage:
    return _in_adapter.validate_python(raw)


# ---------- Outgoing (plain dict builders) ----------

def out_snapshot(snapshot_obj: BaseModel) -> dict:
    return {"type": "snapshot", "data": snapshot_obj.model_dump(mode="json")}


def out_chat(line: BaseModel) -> dict:
    return {"type": "chat", "line": line.model_dump(mode="json")}


def out_stream_start(channel_id: str, speaker_name: str, speaker_id: str) -> dict:
    return {
        "type": "stream_start",
        "channel_id": channel_id,
        "speaker_name": speaker_name,
        "speaker_id": speaker_id,
    }


def out_stream_delta(channel_id: str, delta: str) -> dict:
    return {"type": "stream_delta", "channel_id": channel_id, "delta": delta}


def out_stream_end(channel_id: str, line: BaseModel) -> dict:
    return {"type": "stream_end", "channel_id": channel_id, "line": line.model_dump(mode="json")}


def out_tally(tally: dict[str, int]) -> dict:
    return {"type": "tally", "tally": tally}


def out_approval(yes: int, no: int, defendant_name: str) -> dict:
    return {
        "type": "approval",
        "yes": yes,
        "no": no,
        "defendant_name": defendant_name,
    }


def out_error(message: str) -> dict:
    return {"type": "error", "message": message}


def out_info(message: str) -> dict:
    return {"type": "info", "message": message}


def out_persona_generated(slot_id: int, persona: BaseModel) -> dict:
    return {
        "type": "persona_generated",
        "slot_id": slot_id,
        "persona": persona.model_dump(mode="json"),
    }


def out_persona_failed(slot_id: int, message: str) -> dict:
    return {"type": "persona_failed", "slot_id": slot_id, "message": message}
