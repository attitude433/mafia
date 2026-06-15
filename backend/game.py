"""GameState — the mutable runtime container for one game.

Holds units, channels, phase, day count, and chat history. Page-flips between
phases re-shape which channels are active. All mutations go through methods
here so the WebSocket layer stays thin.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .models import (
    Channel,
    ChannelKind,
    ChatLine,
    GameSnapshot,
    NightState,
    Persona,
    Phase,
    Role,
    SpeakerKind,
    Unit,
    Vote,
)


# ---------- Role config ----------

@dataclass
class RoleConfig:
    mafia: int = 2
    police: int = 1
    doctor: int = 1
    medium: int = 1
    citizen: int = 2

    def total(self) -> int:
        return self.mafia + self.police + self.doctor + self.medium + self.citizen

    def as_role_list(self) -> list[Role]:
        return (
            [Role.MAFIA] * self.mafia
            + [Role.POLICE] * self.police
            + [Role.DOCTOR] * self.doctor
            + [Role.MEDIUM] * self.medium
            + [Role.CITIZEN] * self.citizen
        )


# ---------- GameState ----------

class GameState:
    def __init__(self) -> None:
        self.phase: Phase = Phase.SETUP
        self.day: int = 0
        self.units: list[Unit] = []
        self.channels: dict[str, Channel] = {}
        self.chat: dict[str, list[ChatLine]] = {}   # channel_id -> lines (UI/표시용)
        self.unit_memory: dict[str, list[ChatLine]] = {}  # unit_id -> 그 유닛의 기억
        self.active_channel_id: str | None = None   # GM의 현재 포커스 채널
        self.speaking_order: list[str] = []          # 살아있는 유닛 id 순서
        self.speaker_idx: int = 0
        self.votes: list[Vote] = []
        self.global_system_prompt: str = ""          # 모든 유닛 system 프리픽스

    # ----- 셋업 -----

    def setup(
        self,
        personas: list[Persona],
        role_config: RoleConfig,
        *,
        models: list[str] | None = None,
        shuffle_roles: bool = True,
    ) -> None:
        if role_config.total() != len(personas):
            raise ValueError(
                f"역할 합({role_config.total()})과 페르소나 수({len(personas)})가 다름"
            )

        roles = role_config.as_role_list()
        if shuffle_roles:
            random.shuffle(roles)

        ms = models or [""] * len(personas)
        if len(ms) != len(personas):
            ms = (ms + [""] * len(personas))[:len(personas)]

        self.units = [
            Unit(persona=p, role=r, model=m)
            for p, r, m in zip(personas, roles, ms)
        ]
        self.unit_memory = {u.id: [] for u in self.units}
        self.channels = {}
        self.chat = {}
        self.votes = []
        self.active_channel_id = None
        self._rebuild_speaking_order()
        self._install_public_channel()
        self._install_mafia_channel()
        self.phase = Phase.SETUP
        self.day = 0

    # ----- 페이즈 -----

    def start_day(self) -> None:
        """첫 낮 또는 다음 낮으로 전환. 밤 결과 적용 후 호출."""
        self.day += 1
        self.phase = Phase.DAY_DISCUSSION
        self.votes = []
        self._rebuild_speaking_order()
        self.active_channel_id = "public"

    def start_voting(self) -> None:
        self.phase = Phase.DAY_VOTING
        self.votes = []
        self._rebuild_speaking_order()
        self.active_channel_id = "public"

    def start_night(self) -> None:
        self.phase = Phase.NIGHT
        for u in self.units:
            u.night = NightState()
        self._install_night_channels()
        self.active_channel_id = "mafia" if "mafia" in self.channels else None

    def end_game(self) -> None:
        self.phase = Phase.ENDED

    # ----- 채널 -----

    def _install_public_channel(self) -> None:
        ch = Channel(
            id="public",
            kind=ChannelKind.PUBLIC,
            label="공개 채팅",
            member_ids=[u.id for u in self.alive_units()],
        )
        self.channels[ch.id] = ch
        self.chat.setdefault(ch.id, [])

    def _install_mafia_channel(self) -> None:
        mafia = [u for u in self.alive_units() if u.role is Role.MAFIA]
        if not mafia:
            return
        ch = Channel(
            id="mafia",
            kind=ChannelKind.MAFIA,
            label="마피아 단톡",
            member_ids=[u.id for u in mafia],
        )
        self.channels[ch.id] = ch
        self.chat.setdefault(ch.id, [])

    def _install_night_channels(self) -> None:
        """밤 진입 시 능력자별 1:1 채널 + 영매 채널 (활성 대상 없으면 영매는 생략)."""
        for u in self.alive_units():
            if u.role in (Role.POLICE, Role.DOCTOR):
                cid = f"private:{u.role.value}:{u.id}"
                if cid not in self.channels:
                    self.channels[cid] = Channel(
                        id=cid,
                        kind=ChannelKind.PRIVATE,
                        label=f"{_role_label(u.role)} - {u.name}",
                        member_ids=[u.id],
                    )
                    self.chat.setdefault(cid, [])

        # 영매 채널은 죽은 자가 있어야 의미가 있음
        mediums = [u for u in self.alive_units() if u.role is Role.MEDIUM]
        dead = [u for u in self.units if not u.alive]
        if mediums and dead:
            for m in mediums:
                cid = f"medium:{m.id}:{self.day}"
                if cid not in self.channels:
                    self.channels[cid] = Channel(
                        id=cid,
                        kind=ChannelKind.MEDIUM,
                        label=f"영매 {m.name} ↔ 죽은 자",
                        member_ids=[m.id],
                    )
                    self.chat.setdefault(cid, [])

    # ----- 채팅 -----

    def record_chat(
        self,
        channel_id: str,
        speaker_kind: SpeakerKind,
        speaker_id: str,
        speaker_name: str,
        content: str,
    ) -> ChatLine:
        if channel_id not in self.channels:
            raise KeyError(f"unknown channel: {channel_id}")
        line = ChatLine(
            channel_id=channel_id,
            speaker_kind=speaker_kind,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            content=content,
        )
        self.chat[channel_id].append(line)
        # 현재 채널 멤버 전원의 개인 기억에도 같은 라인을 기록 → 죽어도 사라지지 않음
        ch = self.channels[channel_id]
        for uid in ch.member_ids:
            self.unit_memory.setdefault(uid, []).append(line)
        return line

    def chat_visible_to(self, unit_id: str) -> list[ChatLine]:
        """LLM 컨텍스트 빌드용. 그 유닛의 개인 기억 (시간순)."""
        return list(self.unit_memory.get(unit_id, []))

    # ----- 라운드 로빈 -----

    def _rebuild_speaking_order(self) -> None:
        self.speaking_order = [u.id for u in self.alive_units()]
        self.speaker_idx = 0

    def current_speaker(self) -> Unit | None:
        if not self.speaking_order:
            return None
        uid = self.speaking_order[self.speaker_idx % len(self.speaking_order)]
        return self.unit_by_id(uid)

    def advance_speaker(self) -> Unit | None:
        if not self.speaking_order:
            return None
        self.speaker_idx = (self.speaker_idx + 1) % len(self.speaking_order)
        return self.current_speaker()

    def round_complete(self) -> bool:
        """한 바퀴 다 돌았는지 (idx가 0으로 돌아왔는지)."""
        return self.speaker_idx == 0 and self.speaking_order != []

    # ----- 사망 / 능력 -----

    def kill_unit(self, unit_id: str) -> None:
        u = self.unit_by_id(unit_id)
        if u is None or not u.alive:
            return
        u.alive = False
        # 멤버 리스트에서 제거
        for ch in self.channels.values():
            if unit_id in ch.member_ids:
                ch.member_ids = [m for m in ch.member_ids if m != unit_id]
        # 발언 순서에서 제거
        self.speaking_order = [i for i in self.speaking_order if i != unit_id]
        if self.speaker_idx >= len(self.speaking_order) and self.speaking_order:
            self.speaker_idx %= len(self.speaking_order)

    def record_vote(self, voter_id: str, target_id: str | None, raw: str) -> Vote:
        # 같은 voter의 이전 표 제거 (덮어쓰기)
        self.votes = [v for v in self.votes if v.voter_id != voter_id]
        v = Vote(voter_id=voter_id, target_id=target_id, raw=raw)
        self.votes.append(v)
        return v

    def tally(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for v in self.votes:
            if v.target_id:
                out[v.target_id] = out.get(v.target_id, 0) + 1
        return out

    # ----- 조회 -----

    def unit_by_id(self, uid: str) -> Unit | None:
        return next((u for u in self.units if u.id == uid), None)

    def unit_by_name(self, name: str) -> Unit | None:
        name = name.strip()
        if not name:
            return None
        for u in self.units:
            if u.name == name:
                return u
        # 부분 일치 (LLM이 별명 쓰는 경우)
        for u in self.units:
            if name in u.name or u.name in name:
                return u
        return None

    def alive_units(self) -> list[Unit]:
        return [u for u in self.units if u.alive]

    def winner(self) -> Role | None:
        """승리 판정. 마피아 == 시민진영이거나 더 많으면 마피아 승, 마피아 0 → 시민."""
        alive = self.alive_units()
        mafia = [u for u in alive if u.role is Role.MAFIA]
        others = [u for u in alive if u.role is not Role.MAFIA]
        if not mafia:
            return Role.CITIZEN
        if len(mafia) >= len(others):
            return Role.MAFIA
        return None

    # ----- 스냅샷 -----

    def snapshot(self) -> GameSnapshot:
        speaker = self.current_speaker()
        return GameSnapshot(
            phase=self.phase,
            day=self.day,
            units=self.units,
            channels=list(self.channels.values()),
            active_channel_id=self.active_channel_id,
            speaking_unit_id=speaker.id if speaker else None,
            votes=self.votes,
        )


def _role_label(r: Role) -> str:
    return {
        Role.MAFIA: "마피아",
        Role.POLICE: "경찰",
        Role.DOCTOR: "의사",
        Role.MEDIUM: "영매",
        Role.CITIZEN: "시민",
    }[r]
