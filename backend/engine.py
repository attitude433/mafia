"""GameEngine — glues GameState + LLM + WebSocket.

Each connected GM gets one engine instance (single-game-per-connection for now).
Handlers are async and may stream LLM output via the provided sender callback.

Phase-specific LLM generation (round-robin speech, voting parse, night chats)
lives in `phases.py` and is invoked here.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from . import protocol as p
from .anthropic_client import AnthropicClient, AnthropicError
from .game import GameState, RoleConfig
from .llm import OllamaClient, OllamaError
from .models import Persona
from .persona import (
    fallback_personas,
    generate_one_persona,
    generate_personas,
    manual_persona,
)


Sender = Callable[[dict], Awaitable[None]]
LLMError = (OllamaError, AnthropicError)


class GameEngine:
    def __init__(self, send: Sender, llm) -> None:
        self.send = send
        self.llm = llm
        self.state = GameState()
        self._stop_deliberation = False

    async def handle(self, raw: dict[str, Any]) -> None:
        try:
            msg = p.parse_in(raw)
        except Exception as exc:
            await self.send(p.out_error(f"잘못된 메시지: {exc}"))
            return

        method = getattr(self, f"on_{msg.type}", None)
        if method is None:
            await self.send(p.out_error(f"알 수 없는 type: {msg.type}"))
            return

        try:
            await method(msg)
        except Exception as exc:  # 핸들러 내 예외 보호
            await self.send(p.out_error(f"{msg.type} 처리 실패: {exc}"))

    # ---------- 핸들러 ----------

    async def on_setup(self, msg: p.SetupMsg) -> None:
        await self._apply_provider(
            provider=msg.provider,
            anthropic_api_key=msg.anthropic_api_key,
            anthropic_model=msg.anthropic_model,
            ollama_model=msg.ollama_model,
        )

        rc = RoleConfig(**msg.role_config)
        if rc.total() != msg.count:
            await self.send(p.out_error(
                f"역할 합({rc.total()}) ≠ 유닛 수({msg.count})"
            ))
            return

        personas = await self._collect_personas(msg)
        if not personas:
            return  # 에러는 _collect_personas가 보냄

        models = [item.get("model", "") for item in msg.personas] if msg.personas else []
        self.state.setup(personas, rc, models=models)
        self.state.global_system_prompt = (msg.system_prompt or "").strip()
        await self.send(p.out_info(f"셋업 완료: {len(personas)}명, 역할 배정됨"))
        await self._push_snapshot()

    async def on_start_day(self, _msg: p.StartDayMsg) -> None:
        self.state.start_day()
        await self.send(p.out_info(f"Day {self.state.day} 토론 시작"))
        await self._push_snapshot()

    async def on_start_voting(self, _msg: p.StartVotingMsg) -> None:
        self.state.start_voting()
        await self.send(p.out_info("투표 시작"))
        await self._push_snapshot()

    async def on_start_night(self, _msg: p.StartNightMsg) -> None:
        self.state.start_night()
        await self.send(p.out_info(f"Night {self.state.day} 시작"))
        await self._push_snapshot()

    async def on_next_speaker(self, _msg: p.NextSpeakerMsg) -> None:
        # 호환용 — 채널 사이클로 대체됨. 활성 채널 한 바퀴 돌림.
        from .phases import run_channel_cycle
        ch = self.state.active_channel_id or "public"
        await run_channel_cycle(self, ch)

    async def on_gm_say(self, msg: p.GMSayMsg) -> None:
        line = self.state.record_chat(
            channel_id=msg.channel_id,
            speaker_kind="gm",
            speaker_id="gm",
            speaker_name="GM",
            content=msg.content,
        )
        await self.send(p.out_chat(line))
        # GM이 한 마디 던지면 그 채널 해당 인원이 자동으로 한 바퀴 발언
        from .phases import run_channel_cycle
        await run_channel_cycle(self, msg.channel_id)

    async def on_set_active_channel(self, msg: p.SetActiveChannelMsg) -> None:
        self.state.active_channel_id = msg.channel_id
        await self._push_snapshot()

    async def on_kill_unit(self, msg: p.KillUnitMsg) -> None:
        u = self.state.unit_by_id(msg.unit_id)
        if u is None:
            await self.send(p.out_error("해당 유닛 없음"))
            return
        self.state.kill_unit(msg.unit_id)
        await self.send(p.out_info(f"{u.name} 사망"))
        await self._check_winner()
        await self._push_snapshot()

    async def on_set_night_flag(self, msg: p.SetNightFlagMsg) -> None:
        u = self.state.unit_by_id(msg.unit_id)
        if u is None:
            await self.send(p.out_error("해당 유닛 없음"))
            return
        setattr(u.night, msg.flag, msg.value)
        await self._push_snapshot()

    async def on_apply_night(self, _msg: p.ApplyNightMsg) -> None:
        deaths: list[str] = []
        for u in self.state.alive_units():
            if u.night.targeted_by_mafia and not u.night.protected_by_doctor:
                deaths.append(u.id)
        for uid in deaths:
            killed = self.state.unit_by_id(uid)
            if killed:
                self.state.kill_unit(uid)
        names = ", ".join(self.state.unit_by_id(d).name for d in deaths) or "없음"
        await self.send(p.out_info(f"밤 결과 적용 — 사망: {names}"))
        await self._check_winner()
        await self._push_snapshot()

    async def on_summon_dead(self, msg: p.SummonDeadMsg) -> None:
        ch = self.state.channels.get(msg.medium_channel_id)
        dead = self.state.unit_by_id(msg.dead_unit_id)
        if ch is None or dead is None:
            await self.send(p.out_error("영매 채널 또는 죽은 유닛 없음"))
            return
        if dead.id not in ch.member_ids:
            ch.member_ids.append(dead.id)
        await self.send(p.out_info(f"{dead.name}을(를) 영매 채널로 호출"))
        await self._push_snapshot()

    async def on_speak_in_channel(self, msg: p.SpeakInChannelMsg) -> None:
        from .phases import speak_unit_in_channel
        await speak_unit_in_channel(self, msg.unit_id, msg.channel_id)

    async def on_speak_dead(self, msg: p.SpeakDeadMsg) -> None:
        from .phases import speak_dead_in_medium
        await speak_dead_in_medium(self, msg.dead_unit_id, msg.medium_channel_id)

    async def on_final_defense(self, msg: p.FinalDefenseMsg) -> None:
        from .phases import run_final_defense
        await run_final_defense(self, msg.unit_id)

    async def on_ai_vote(self, msg: p.AIVoteMsg) -> None:
        from .phases import run_ai_vote
        await run_ai_vote(self, reset=msg.reset)

    async def on_approval_vote(self, msg: p.ApprovalVoteMsg) -> None:
        from .phases import run_approval_vote
        await run_approval_vote(self, msg.defendant_id)

    async def on_mafia_target_vote(self, msg: p.MafiaTargetVoteMsg) -> None:
        from .phases import run_mafia_target_vote
        await run_mafia_target_vote(self, auto_apply=msg.auto_apply)

    async def on_mafia_deliberate(self, msg: p.MafiaDeliberateMsg) -> None:
        from .phases import run_mafia_deliberation
        self._stop_deliberation = False
        await run_mafia_deliberation(self, max_speeches=msg.max_speeches)

    async def on_stop_deliberation(self, _msg: p.StopDeliberationMsg) -> None:
        self._stop_deliberation = True
        await self.send(p.out_info("토론 중단 요청 — 현재 발언 끝나면 정지"))

    async def on_end_game(self, _msg: p.EndGameMsg) -> None:
        self.state.end_game()
        await self._push_snapshot()

    async def on_request_snapshot(self, _msg: p.RequestSnapshotMsg) -> None:
        await self._push_snapshot()

    async def on_gen_one_persona(self, msg: p.GenOnePersonaMsg) -> None:
        try:
            persona = await generate_one_persona(
                self.llm,
                theme=msg.theme,
                existing_names=msg.existing_names,
            )
        except (*LLMError, ValueError) as exc:
            await self.send(p.out_persona_failed(msg.slot_id, str(exc)))
            return
        await self.send(p.out_persona_generated(msg.slot_id, persona))

    async def on_config_provider(self, msg: p.ConfigProviderMsg) -> None:
        await self._apply_provider(
            provider=msg.provider,
            anthropic_api_key=msg.anthropic_api_key,
            anthropic_model=msg.anthropic_model,
            ollama_model=msg.ollama_model,
        )
        await self.send(p.out_info(f"프로바이더 설정: {msg.provider}"))

    # ---------- 내부 유틸 ----------

    async def _collect_personas(self, msg: p.SetupMsg) -> list[Persona]:
        if msg.persona_mode == "manual":
            try:
                return [
                    manual_persona(
                        name=item.get("name", ""),
                        summary=item.get("summary", ""),
                        style=item.get("style", ""),
                        quirks=item.get("quirks", ""),
                    )
                    for item in msg.personas
                ]
            except ValueError as exc:
                await self.send(p.out_error(f"수동 페르소나 오류: {exc}"))
                return []

        # auto — 한 명씩 생성, 진행률 푸시. 도중 실패 시 부분 결과 + 폴백.
        async def report(i: int, total: int, persona) -> None:
            await self.send(p.out_info(
                f"페르소나 생성 {i}/{total}: {persona.name} — {persona.summary}"
            ))

        partial: list[Persona] = []
        try:
            partial = await generate_personas(
                self.llm, msg.count,
                theme=msg.theme,
                progress=report,
                partial=partial,
            )
        except (*LLMError, ValueError) as exc:
            done = len(partial)
            short = msg.count - done
            if done > 0:
                await self.send(p.out_info(
                    f"{done}/{msg.count}명 생성 후 실패 — 남은 {short}명은 폴백으로 채움: {exc}"
                ))
            else:
                await self.send(p.out_info(f"자동 생성 실패, 폴백 사용: {exc}"))
            used = {x.name for x in partial}
            for fb in fallback_personas(short):
                if fb.name in used:
                    continue
                partial.append(fb)
                used.add(fb.name)
                if len(partial) >= msg.count:
                    break
        return partial

    async def _push_snapshot(self) -> None:
        await self.send(p.out_snapshot(self.state.snapshot()))

    async def _apply_provider(
        self,
        *,
        provider: str,
        anthropic_api_key: str | None,
        anthropic_model: str,
        ollama_model: str | None,
    ) -> None:
        """LLM 클라이언트 교체. 셋업/설정 메시지에서 호출."""
        if provider == "anthropic":
            if not anthropic_api_key:
                await self.send(p.out_error("Anthropic API 키가 비어있습니다"))
                return
            try:
                new = AnthropicClient(
                    api_key=anthropic_api_key,
                    model=anthropic_model or "claude-haiku-4-5-20251001",
                )
            except AnthropicError as exc:
                await self.send(p.out_error(f"Anthropic 클라이언트 초기화 실패: {exc}"))
                return
        elif provider == "ollama":
            new = OllamaClient(model=ollama_model)
        else:
            await self.send(p.out_error(f"알 수 없는 provider: {provider}"))
            return

        old = self.llm
        self.llm = new
        try:
            await old.aclose()
        except Exception:
            pass

    async def _check_winner(self) -> None:
        w = self.state.winner()
        if w is not None:
            self.state.end_game()
            label = "마피아 승리" if w.value == "mafia" else "시민 진영 승리"
            await self.send(p.out_info(f"게임 종료: {label}"))
