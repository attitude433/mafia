"""Phase-specific LLM orchestration.

Engine handlers delegate the heavy lifting (prompt building, streaming,
parsing) here. Day discussion / voting / night chats each route through
one of the functions below.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from . import protocol as p
from .anthropic_client import AnthropicError
from .llm import ChatMessage, OllamaError
from .models import Phase, Role
from .prompts import build_day_messages, build_night_messages

LLM_ERRORS = (OllamaError, AnthropicError)

if TYPE_CHECKING:
    from .engine import GameEngine


# ---------- Auto cycle (GM 발언 후 채널 인원 순회) ----------

async def run_channel_cycle(engine: "GameEngine", channel_id: str) -> None:
    """채널 종류에 따라 해당 인원이 한 라운드씩 발언한다.

    이 라운드의 모든 발언자는 **사이클 시작 시점의 동일한 컨텍스트**를 보고 답한다.
    즉 두 번째 발언자는 첫 번째 발언자의 답을 보지 않는다 — 서로 모방·동조 차단.

    다음 사이클(GM 다음 메시지)부터는 이번 라운드 7개 답변이 모두 컨텍스트에 들어감.
    """
    state = engine.state
    ch = state.channels.get(channel_id)
    if ch is None:
        await engine.send(p.out_error(f"채널 없음: {channel_id}"))
        return

    speaker_ids = _cycle_speakers(state, channel_id, ch)
    if not speaker_ids:
        await engine.send(p.out_info(f"{ch.label}에 발언 가능한 인원 없음"))
        return

    is_public = channel_id == "public"
    is_voting = is_public and state.phase is Phase.DAY_VOTING

    # 1) 사이클 시작 시점의 컨텍스트로 모든 발언자의 프롬프트를 미리 빌드
    prebuilt: list[tuple] = []
    for uid in speaker_ids:
        speaker = state.unit_by_id(uid)
        if speaker is None or not speaker.alive:
            continue
        messages = (
            build_day_messages(state, speaker)
            if is_public
            else build_night_messages(state, speaker, channel_id)
        )
        prebuilt.append((speaker, messages))

    # 2) 순차로 스트리밍 (UI에는 차례로 나타나지만, 각 프롬프트는 이미 고정됨)
    for speaker, messages in prebuilt:
        text = await _stream_unit_speech(
            engine,
            channel_id=channel_id,
            speaker_id=speaker.id,
            speaker_name=speaker.name,
            messages=messages,
            model=speaker.model or None,
        )
        if text is not None and is_voting:
            target = _parse_vote(text, state, voter_id=speaker.id)
            state.record_vote(
                voter_id=speaker.id,
                target_id=target.id if target else None,
                raw=text,
            )
            await engine.send(p.out_tally(state.tally()))

    await engine.send(p.out_snapshot(state.snapshot()))


def _cycle_speakers(state, channel_id: str, ch) -> list[str]:
    if channel_id == "public":
        return [u.id for u in state.alive_units()]
    if channel_id == "mafia":
        return [u.id for u in state.alive_units() if u.role is Role.MAFIA]
    # private/medium 등: 채널 멤버 중 살아있는 사람
    out = []
    for uid in ch.member_ids:
        u = state.unit_by_id(uid)
        if u and u.alive:
            out.append(uid)
    return out


# ---------- Night ----------

async def speak_unit_in_channel(
    engine: "GameEngine",
    unit_id: str,
    channel_id: str,
) -> None:
    """특정 채널에서 특정 유닛이 발언 (마피아/직업 단톡, 1:1, 영매 등)."""
    state = engine.state
    speaker = state.unit_by_id(unit_id)
    if speaker is None or not speaker.alive:
        await engine.send(p.out_error("발언자 유닛을 찾을 수 없음"))
        return

    ch = state.channels.get(channel_id)
    if ch is None or speaker.id not in ch.member_ids:
        await engine.send(p.out_error("그 채널에 발언 권한 없음"))
        return

    await _stream_unit_speech(
        engine,
        channel_id=channel_id,
        speaker_id=speaker.id,
        speaker_name=speaker.name,
        messages=build_night_messages(state, speaker, channel_id),
        model=speaker.model or None,
    )


async def run_final_defense(engine: "GameEngine", unit_id: str | None) -> None:
    """투표 최다 득표자가 공개 채팅에서 최후의 변론을 한다."""
    state = engine.state
    target_id = unit_id or _top_voted_id(state)
    if target_id is None:
        await engine.send(p.out_error("최후의 변론 대상이 없음 (투표 미진행)"))
        return

    speaker = state.unit_by_id(target_id)
    if speaker is None or not speaker.alive:
        await engine.send(p.out_error("대상이 살아있지 않음"))
        return

    # GM 알림 메시지 → 자동 사이클을 막기 위해 직접 record_chat + send만 사용
    ann = state.record_chat(
        channel_id="public",
        speaker_kind="system",
        speaker_id="system",
        speaker_name="진행",
        content=f"{speaker.name}이(가) 최다 득표. 최후의 변론을 시작합니다.",
    )
    await engine.send(p.out_chat(ann))

    extra = ChatMessage(
        "user",
        "[중요] 너는 이번 투표에서 가장 많은 표를 받아 곧 처형될 위기다. "
        "지금이 마지막 변론 기회다. 결백 호소, 다른 사람 지목, 마지막 호소 등 "
        "페르소나에 충실하게, 길지 않게(3~5문장) 말하라. 본문만 출력.",
    )
    messages = build_day_messages(state, speaker) + [extra]

    await _stream_unit_speech(
        engine,
        channel_id="public",
        speaker_id=speaker.id,
        speaker_name=f"{speaker.name} (변론)",
        messages=messages,
        model=speaker.model or None,
    )
    await engine.send(p.out_snapshot(state.snapshot()))


async def run_ai_vote(engine: "GameEngine", *, reset: bool = True) -> None:
    """살아있는 유닛 전원이 한 명씩 이름만 출력하는 구조화 투표."""
    state = engine.state
    if state.phase is not Phase.DAY_VOTING:
        await engine.send(p.out_error("AI 투표는 투표 페이즈에서만 가능"))
        return

    if reset:
        state.votes = []
        await engine.send(p.out_tally({}))

    voters = list(state.alive_units())
    for voter in voters:
        target = await _ai_pick_vote(engine, voter)
        state.record_vote(
            voter_id=voter.id,
            target_id=target.id if target else None,
            raw=(target.persona.name if target else ""),
        )
        line = state.record_chat(
            channel_id="public",
            speaker_kind="system",
            speaker_id="system",
            speaker_name="투표",
            content=f"{voter.persona.name} → {target.persona.name if target else '(미결정)'}",
        )
        await engine.send(p.out_chat(line))
        await engine.send(p.out_tally(state.tally()))

    await engine.send(p.out_snapshot(state.snapshot()))


async def _ai_pick_vote(engine: "GameEngine", voter):
    state = engine.state
    alive_others = [u for u in state.alive_units() if u.id != voter.id]
    cand = "\n".join(f"- {u.persona.name}" for u in alive_others)
    extra = ChatMessage(
        "user",
        "이제 투표 결정 시간이다.\n"
        "다른 말 일절 없이, 아래 후보 중 한 명의 이름만 정확히 그대로 출력하라.\n"
        f"후보:\n{cand}\n\n"
        "출력 예시: 윌리엄 그레이브스"
    )
    messages = build_day_messages(state, voter) + [extra]
    try:
        text = await engine.llm.chat(
            messages, temperature=0.4, max_tokens=40,
            model=voter.model or None,
        )
    except LLM_ERRORS as exc:
        await engine.send(p.out_error(f"AI 투표 실패 ({voter.persona.name}): {exc}"))
        return None
    text = text.strip().splitlines()[0].strip().strip("'\"")
    return state.unit_by_name(text)


async def run_mafia_deliberation(
    engine: "GameEngine", *, max_speeches: int = 20,
) -> None:
    """마피아끼리 한 명씩 돌아가며 발언하고, 표적이 만장일치되면 자동 종료."""
    state = engine.state
    mafias = [u for u in state.alive_units() if u.role is Role.MAFIA]
    if not mafias:
        await engine.send(p.out_error("살아있는 마피아 없음"))
        return
    candidates = [u for u in state.alive_units() if u.role is not Role.MAFIA]
    if not candidates:
        await engine.send(p.out_error("표적이 될 시민 없음"))
        return

    # 마피아가 1명이면 한 번만 발언하고 그 사람의 지목 사용
    if len(mafias) == 1:
        solo = mafias[0]
        text = await _stream_unit_speech(
            engine,
            channel_id="mafia",
            speaker_id=solo.id,
            speaker_name=solo.name,
            messages=build_night_messages(state, solo, "mafia"),
            model=solo.model or None,
        )
        if text:
            t = _extract_mafia_target(text, state, solo.id)
            if t:
                _apply_mafia_target(state, t)
                await _announce_consensus(engine, state, t, count=1)
        return

    last_targets: dict[str, str] = {}   # mafia_id -> last target_id
    count = 0
    idx = 0
    no_target_streak = 0    # 연속으로 표적이 안 잡힌 발언 수

    while count < max_speeches:
        if engine._stop_deliberation:
            await engine.send(p.out_info("토론 중단됨"))
            engine._stop_deliberation = False
            return

        speaker = mafias[idx % len(mafias)]
        idx += 1
        messages = build_night_messages(state, speaker, "mafia") + [
            ChatMessage(
                "user",
                "[필수] 너의 발언 마지막 한 문장은 반드시 "
                "'나는 ○○를 표적으로 지목한다.' 형식이어야 한다. "
                "○○는 살아있는 시민(비-마피아) 한 명의 이름. "
                "이 형식이 없으면 무효 발언이다."
            )
        ]
        text = await _stream_unit_speech(
            engine,
            channel_id="mafia",
            speaker_id=speaker.id,
            speaker_name=speaker.name,
            messages=messages,
            model=speaker.model or None,
        )
        count += 1

        if text:
            t = _extract_mafia_target(text, state, speaker.id)
            if t:
                last_targets[speaker.id] = t.id
                no_target_streak = 0
            else:
                no_target_streak += 1
        else:
            no_target_streak += 1

        # 조기 종료: 마피아 수만큼 연속으로 표적 없음 → 진척 없음 판정
        if no_target_streak >= max(2, len(mafias) * 2):
            await engine.send(p.out_info(
                f"{count}회 발언했지만 유효한 표적이 안 나옵니다. 토론 종료. "
                "'마피아 표적 결정' 버튼으로 강제 투표 권장"
            ))
            return

        # 합의 확인
        if len(last_targets) >= len(mafias):
            uniq = set(last_targets[m.id] for m in mafias if m.id in last_targets)
            if len(uniq) == 1:
                target_id = next(iter(uniq))
                target_unit = state.unit_by_id(target_id)
                _apply_mafia_target(state, target_unit)
                await _announce_consensus(engine, state, target_unit, count=count)
                return

    await engine.send(p.out_info(
        f"{max_speeches}회 발언 후에도 합의 안 됨. '마피아 표적 결정' 버튼으로 다수결 처리 권장"
    ))


def _extract_mafia_target(text: str, state, voter_id: str):
    """마피아 발언에서 지목된 시민 한 명을 추출. 비-마피아·alive·자기 자신 제외."""
    eligible = [u for u in state.alive_units() if u.role is not Role.MAFIA]

    # 1) 명시적 동사 패턴 (투표/지목/선택/뽑)
    for m in reversed(list(_VOTE_RE.finditer(text))):
        name = m.group(1).strip()
        u = state.unit_by_name(name)
        if u and u in eligible:
            return u

    # 2) 발언 마지막 부분에 등장한 시민 이름
    best_pos = -1
    best = None
    for u in eligible:
        idx = text.rfind(u.persona.name)
        if idx > best_pos:
            best_pos = idx
            best = u
    return best


def _apply_mafia_target(state, target_unit) -> None:
    for u in state.units:
        u.night.targeted_by_mafia = (u.id == target_unit.id)


async def _announce_consensus(engine, state, target_unit, *, count: int) -> None:
    line = state.record_chat(
        channel_id="mafia",
        speaker_kind="system",
        speaker_id="system",
        speaker_name="진행",
        content=f"마피아 합의 도달 — 표적: {target_unit.persona.name} ({count}회 발언 후)",
    )
    await engine.send(p.out_chat(line))
    await engine.send(p.out_snapshot(state.snapshot()))


async def run_mafia_target_vote(engine: "GameEngine", *, auto_apply: bool = True) -> None:
    """살아있는 마피아 전원이 표적을 한 명씩 지목. 최다 득표자 자동 표적화."""
    state = engine.state
    mafias = [u for u in state.alive_units() if u.role is Role.MAFIA]
    if not mafias:
        await engine.send(p.out_error("살아있는 마피아 없음"))
        return
    candidates = [u for u in state.alive_units() if u.role is not Role.MAFIA]
    if not candidates:
        await engine.send(p.out_error("표적이 될 시민이 없음"))
        return

    counts: dict[str, int] = {}
    for voter in mafias:
        target = await _ai_pick_target(engine, voter, candidates)
        if target:
            counts[target.id] = counts.get(target.id, 0) + 1
        line = state.record_chat(
            channel_id="mafia",
            speaker_kind="system",
            speaker_id="system",
            speaker_name="표적 투표",
            content=f"{voter.persona.name} → {target.persona.name if target else '(미결정)'}",
        )
        await engine.send(p.out_chat(line))

    if not counts:
        await engine.send(p.out_info("표적 투표 결과 없음 — 모두 미결정"))
        return

    top_id = max(counts.items(), key=lambda kv: kv[1])[0]
    top = state.unit_by_id(top_id)

    summary = state.record_chat(
        channel_id="mafia",
        speaker_kind="system",
        speaker_id="system",
        speaker_name="진행",
        content=f"마피아 표적 결정: {top.persona.name} (득표 {counts[top_id]})",
    )
    await engine.send(p.out_chat(summary))

    if auto_apply:
        # 다른 모든 유닛의 mafia 표적 해제, 결정된 한 명만 표시
        for u in state.units:
            u.night.targeted_by_mafia = (u.id == top_id)
        await engine.send(p.out_info(f"표적 플래그 설정: {top.persona.name}"))
        await engine.send(p.out_snapshot(state.snapshot()))


async def _ai_pick_target(engine, voter, candidates):
    state = engine.state
    cand_str = "\n".join(f"- {u.persona.name}" for u in candidates)
    extra = ChatMessage(
        "user",
        "[표적 결정 시간]\n"
        "오늘 밤 너희 마피아가 탈락시킬 시민 한 명을 지금 결정한다.\n"
        "다른 말 일절 없이, 아래 후보 중 한 명의 이름만 정확히 그대로 출력하라.\n"
        f"후보:\n{cand_str}\n\n"
        "출력 예시: 김상철"
    )
    messages = build_night_messages(state, voter, "mafia") + [extra]
    try:
        text = await engine.llm.chat(
            messages, temperature=0.4, max_tokens=40,
            model=voter.model or None,
        )
    except LLM_ERRORS as exc:
        await engine.send(p.out_error(f"표적 투표 실패 ({voter.persona.name}): {exc}"))
        return None
    text = text.strip().splitlines()[0].strip().strip("'\"")
    u = state.unit_by_name(text)
    if u and u.alive and u.role is not Role.MAFIA:
        return u
    return None


async def run_approval_vote(engine: "GameEngine", defendant_id: str | None) -> None:
    """피고인을 처형할지 살아있는 나머지 유닛이 찬/반 투표."""
    state = engine.state
    target_id = defendant_id or _top_voted_id(state)
    defendant = state.unit_by_id(target_id) if target_id else None
    if defendant is None or not defendant.alive:
        await engine.send(p.out_error("찬반 투표 대상이 없음"))
        return

    voters = [u for u in state.alive_units() if u.id != defendant.id]
    if not voters:
        await engine.send(p.out_error("투표 가능 인원 없음"))
        return

    yes = 0
    no = 0
    for voter in voters:
        decision = await _ai_pick_approval(engine, voter, defendant.persona.name)
        if decision is True:
            yes += 1
            text = "찬성"
        elif decision is False:
            no += 1
            text = "반대"
        else:
            text = "(미결정)"
        line = state.record_chat(
            channel_id="public",
            speaker_kind="system",
            speaker_id="system",
            speaker_name="찬반",
            content=f"{voter.persona.name}: {text}",
        )
        await engine.send(p.out_chat(line))
        await engine.send(p.out_approval(yes, no, defendant.persona.name))

    summary = state.record_chat(
        channel_id="public",
        speaker_kind="system",
        speaker_id="system",
        speaker_name="진행",
        content=f"{defendant.persona.name} 찬반 투표 결과 — 찬성 {yes} / 반대 {no}",
    )
    await engine.send(p.out_chat(summary))
    await engine.send(p.out_snapshot(state.snapshot()))


async def _ai_pick_approval(engine, voter, defendant_name: str) -> bool | None:
    state = engine.state
    extra = ChatMessage(
        "user",
        f"{defendant_name}을(를) 이번 라운드에서 탈락(처형)시키는 것에 대해 찬반을 결정하라.\n"
        "다른 말 일절 없이, 정확히 '찬성' 또는 '반대' 두 글자 중 하나만 출력하라."
    )
    messages = build_day_messages(state, voter) + [extra]
    try:
        text = await engine.llm.chat(
            messages, temperature=0.4, max_tokens=20,
            model=voter.model or None,
        )
    except LLM_ERRORS as exc:
        await engine.send(p.out_error(f"찬반 실패 ({voter.persona.name}): {exc}"))
        return None
    t = text.strip().splitlines()[0].strip()
    if "찬성" in t:
        return True
    if "반대" in t:
        return False
    return None


def _top_voted_id(state) -> str | None:
    tally = state.tally()
    if not tally:
        return None
    # 최다 득표. 동률이면 first encountered.
    top_id = max(tally.items(), key=lambda kv: kv[1])[0]
    return top_id


async def speak_dead_in_medium(
    engine: "GameEngine",
    dead_unit_id: str,
    medium_channel_id: str,
) -> None:
    """영매 채널에서 죽은 자가 발언. 페르소나는 유지."""
    state = engine.state
    dead = state.unit_by_id(dead_unit_id)
    ch = state.channels.get(medium_channel_id)
    if dead is None or ch is None or dead.alive:
        await engine.send(p.out_error("죽은 자/영매 채널 검증 실패"))
        return

    await _stream_unit_speech(
        engine,
        channel_id=medium_channel_id,
        speaker_id=dead.id,
        speaker_name=f"{dead.name}(死)",
        messages=build_night_messages(state, dead, medium_channel_id),
        model=dead.model or None,
    )


# ---------- Internal ----------

async def _stream_unit_speech(
    engine: "GameEngine",
    *,
    channel_id: str,
    speaker_id: str,
    speaker_name: str,
    messages,
    model: str | None = None,
) -> str | None:
    """공통 스트리밍 루틴 — 토큰 푸시, 최종 라인 기록·푸시."""
    use_model = model or getattr(engine.llm, "model", "?")
    mem = engine.state.unit_memory.get(speaker_id, [])
    print(f"[speech] channel={channel_id} speaker={speaker_name} model={use_model} memory_lines={len(mem)}")
    if mem:
        last3 = mem[-3:]
        for ln in last3:
            print(f"   memo: [{ln.channel_id}] {ln.speaker_name}: {ln.content[:80]}")
    await engine.send(p.out_stream_start(channel_id, speaker_name, speaker_id))
    chunks: list[str] = []
    err: str | None = None
    try:
        async for delta in engine.llm.chat_stream(
            messages,
            temperature=0.85,
            top_p=0.9,
            max_tokens=150,
            model=model,
        ):
            chunks.append(delta)
            await engine.send(p.out_stream_delta(channel_id, delta))
    except LLM_ERRORS as exc:
        err = str(exc)
        print(f"[speech] LLM error: {exc}")
        await engine.send(p.out_error(f"LLM 호출 실패: {exc}"))

    text = _clean_output("".join(chunks))
    text = _trim_to_sentences(text, max_sentences=2)
    print(f"[speech] received {len(chunks)} chunks, text_len={len(text)}")

    if not text:
        # 빈 응답이어도 버블은 닫아준다
        placeholder = f"(빈 응답{f': {err}' if err else ''})"
        line = engine.state.record_chat(
            channel_id=channel_id,
            speaker_kind="system",
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            content=placeholder,
        )
        await engine.send(p.out_stream_end(channel_id, line))
        return None

    line = engine.state.record_chat(
        channel_id=channel_id,
        speaker_kind="unit",
        speaker_id=speaker_id,
        speaker_name=speaker_name,
        content=text,
    )
    await engine.send(p.out_stream_end(channel_id, line))
    return text


# ---------- 후처리 ----------

_SENT_END_RE = re.compile(r"[\.!\?。\?\!…]+(?=\s|$)")
_LEADING_PREFIX_RE = re.compile(r"^\s*(\[.*?\]|\(.*?\)|[가-힣A-Za-z0-9_]+:)\s*")


def _clean_output(text: str) -> str:
    """LLM 출력 정리 — 선두 공백/줄바꿈, '[GM]:'·'이름:' 같은 접두사 제거."""
    if not text:
        return ""
    text = text.lstrip()
    # 화자 라벨/접두사 반복 제거 (2회까지)
    for _ in range(2):
        m = _LEADING_PREFIX_RE.match(text)
        if m:
            text = text[m.end():].lstrip()
        else:
            break
    return text.strip()


def _trim_to_sentences(text: str, *, max_sentences: int) -> str:
    """텍스트를 N문장까지만 남기고 자른다. 끝이 미완성이면 마지막 완성 문장까지로.

    한국어 .!? 종결 + … 기준. 종결 부호가 하나도 없으면 원본 유지.
    """
    if not text:
        return text
    ends = [m.end() for m in _SENT_END_RE.finditer(text)]
    if not ends:
        return text   # 문장 끝 없음 — 자르면 더 어색하니 그대로
    n = min(len(ends), max_sentences)
    cut = ends[n - 1]
    return text[:cut].strip()


# ---------- Vote parsing ----------

# "○○를 투표/지목/선택/의심" 패턴 (이름은 한국어 단어 한 덩어리)
_VOTE_RE = re.compile(r"([\w가-힣]+)\s*[을를]?\s*(?:투표|지목|선택|의심|뽑)")


def _parse_vote(text: str, state, voter_id: str | None = None):
    """발언에서 투표 의도를 추출. 명시적 패턴 우선, 실패 시 마지막 이름 언급으로 폴백."""
    # 1) 명시적 동사 + 이름 패턴
    for m in reversed(list(_VOTE_RE.finditer(text))):
        name = m.group(1).strip()
        u = state.unit_by_name(name)
        if u and u.alive and u.id != voter_id:
            return u

    # 2) 폴백 — 발언에서 가장 늦게 등장한 살아있는 유닛 이름 (자기 자신 제외)
    alive = [u for u in state.alive_units() if u.id != voter_id]
    best_pos = -1
    best_unit = None
    for u in alive:
        idx = text.rfind(u.name)
        if idx < 0 and u.persona.name:
            tail = u.persona.name.split()[-1]
            if tail and tail != u.persona.name:
                idx = text.rfind(tail)
        if idx > best_pos:
            best_pos = idx
            best_unit = u
    return best_unit
