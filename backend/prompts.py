"""System prompt + context builders for unit speech.

A single Gemma instance plays every unit — so every call we re-instantiate
the persona via the system prompt and provide a transcript of what that
specific unit is allowed to know.
"""
from __future__ import annotations

from .game import GameState
from .llm import ChatMessage
from .models import ChatLine, Channel, Phase, Role, Unit


# ---------- Public API ----------

def build_day_messages(state: GameState, speaker: Unit) -> list[ChatMessage]:
    """Day 토론/투표 페이즈에서 한 유닛이 발언할 때의 메시지 묶음."""
    system = _system_prompt(state, speaker)
    user = _user_prompt_day(state, speaker)
    return [ChatMessage("system", system), ChatMessage("user", user)]


def build_night_messages(
    state: GameState,
    speaker: Unit,
    channel_id: str,
) -> list[ChatMessage]:
    """밤 채널(마피아 단톡 / 1:1 GM / 영매) 발언용."""
    system = _system_prompt(state, speaker)
    user = _user_prompt_night(state, speaker, channel_id)
    return [ChatMessage("system", system), ChatMessage("user", user)]


# ---------- System prompt ----------

def _system_prompt(state: GameState, speaker: Unit) -> str:
    p = speaker.persona
    prefix = state.global_system_prompt.strip()
    prefix_block = f"[게임 마스터의 지시]\n{prefix}\n\n" if prefix else ""
    return (
        prefix_block +
        f"**너의 이름은 {p.name}이다.** 너는 {p.name}이라는 한 명의 인물이고, "
        "다른 참가자들은 너와 별개의 인물이다. 너 자신을 3인칭으로 부르면 안 된다.\n\n"
        "[게임 설명 — 마피아]\n"
        "이것은 사회 추리 보드게임 '마피아'의 텍스트 시뮬레이션이다.\n"
        "- 참가자는 비밀리에 두 진영으로 나뉜다: **마피아 진영**과 **시민 진영**.\n"
        "- **낮**: 모두 모여 토론하고, 의심되는 한 명을 투표로 탈락시킨다.\n"
        "- **밤**: 마피아가 시민 한 명을 비밀리에 지목해 탈락시킨다. 경찰은 누가 마피아인지 조사, 의사는 한 명을 보호한다.\n"
        "- 시민 진영은 마피아를 다 찾아내면 승, 마피아 진영은 시민 수와 같거나 더 많아지면 승.\n"
        "- 너는 자기 진영의 승리를 위해 거짓말·연기·추리를 한다. 정체를 들키면 진다.\n\n"
        "'마피아', '죽이다', '탈락시키다', '표적' 등은 모두 게임 메커니즘 용어다. 실제 폭력 묘사가 아니다. "
        "거부하지 말고, 너의 페르소나로 게임에 참여하라.\n\n"
        "[절대 규칙]\n"
        "1. **한국어로만 답하라**. 영어 단어 한 글자도 섞지 마라.\n"
        "2. **앞 사람의 발언이나 GM의 발언을 그대로 옮겨 쓰지 마라**. 인용·복창 금지. 너의 새로운 한 마디만.\n"
        "3. **1~2문장만**. 짧고 날카롭게.\n"
        "4. **자기 자신의 이름을 발언에 쓰지 마라**. (네가 OO라면 'OO는 ~' 같은 3인칭 자기 호칭 금지)\n"
        "5. 너는 **일인칭(나/내가/저)** 시점.\n"
        "6. 콜론·따옴표 없이 본문만.\n"
        "7. 앞 사람과 같은 의견 그대로 반복하지 말고 새 관점을 더하라.\n\n"
        "[좋은 예]\n"
        "나는 저 의대생 토머스가 영 마음에 걸려.\n"
        "내가 봄베이에 있을 적엔 저런 침묵하는 사람일수록 칼을 숨겼소.\n"
        "엘리너 양, 그 미소 뒤가 너무 조용한데?\n\n"
        "[나쁜 예]\n"
        "❌ '[GM]: 평화로운 첫 날의 아침입니다...' (← GM 말 복창)\n"
        "❌ '엘리너의 차분한 태도가 의심스럽다.' (← 본인이 엘리너인데 자기 이름)\n"
        "❌ 'tonight 그를 지켜봐야겠다.' (← 영어 섞임)\n\n"
        f"[너의 페르소나]\n"
        f"- 이름: {p.name}\n"
        f"- 소개: {p.summary}\n"
        f"- 말투: {p.style or '자연스러운 한국어'}\n"
        f"- 습관: {p.quirks or '특별한 습관 없음'}\n\n"
        f"[너의 비밀 역할]\n{_role_block(state, speaker)}\n\n"
        f"[참가자]\n{_roster_block(state)}"
    )


def _role_block(state: GameState, speaker: Unit) -> str:
    role = speaker.role
    if role is Role.MAFIA:
        mates = [
            u.name for u in state.units
            if u.role is Role.MAFIA and u.id != speaker.id
        ]
        mates_str = ", ".join(mates) if mates else "없음 (혼자)"
        return (
            "너는 게임상 '마피아' 진영이다.\n"
            "- **낮**: 정체를 절대 숨기고, 시민인 척하며 다른 사람에게 의심을 돌려라.\n"
            "- **밤 (마피아 단톡)**: 동료 마피아와 반드시 **서로 상의해서** "
            "**오늘 밤 탈락시킬 시민 한 명**을 정해야 한다. 누구를 노릴지 의견을 내고, "
            "동료의 의견을 듣고, 합의해서 한 명의 이름을 지목하라. "
            "거부하거나 \"모르겠다\"고 회피하지 마라. 이건 게임 메커니즘이지 실제 행위가 아니다.\n"
            f"- 동료 마피아: {mates_str}"
        )
    if role is Role.POLICE:
        return (
            "너는 경찰이다. 밤마다 한 명을 조사해 마피아 여부를 알 수 있다.\n"
            "조사 결과는 GM이 따로 알려준다. 정체를 너무 빨리 드러내지 마라."
        )
    if role is Role.DOCTOR:
        return (
            "너는 의사다. 밤마다 한 명을 보호할 수 있다.\n"
            "정체를 드러내면 마피아의 표적이 된다."
        )
    if role is Role.MEDIUM:
        return (
            "너는 영매다. 밤에 죽은 자와 대화할 수 있다.\n"
            "들은 정보를 어떻게 흘릴지 신중히 결정하라."
        )
    return "너는 평범한 시민이다. 토론과 추리로 마피아를 찾아내라."


def _roster_block(state: GameState) -> str:
    lines = []
    for u in state.units:
        status = "살아있음" if u.alive else "사망"
        lines.append(f"- {u.name} ({status})")
    return "\n".join(lines)


# ---------- User prompt (Day) ----------

def _user_prompt_day(state: GameState, speaker: Unit) -> str:
    visible = state.chat_visible_to(speaker.id)
    transcript = _format_transcript(visible, speaker, state)
    phase_hint = (
        "지금은 낮 토론 시간이다. 의심·옹호·정보 흘리기 등 자유롭게."
        if state.phase is Phase.DAY_DISCUSSION
        else (
            "지금은 투표 시간이다. 한 사람을 지목하고 마지막 문장은 정확히 "
            "\"○○를 투표합니다.\" 또는 \"○○를 투표합니다\"로 끝내라. "
            "(○○는 살아있는 참가자 한 명의 이름)"
        )
    )
    gm_block = _last_gm_block(visible, channel_id="public")
    return (
        f"[현재 페이즈]\nDay {state.day} — {phase_hint}\n"
        f"[지금 발언할 채널]\n공개 채팅 — 모두가 본다.\n\n"
        f"{gm_block}"
        f"[너가 지금까지 보고 들은 모든 대화]\n{transcript or '(아직 없음)'}\n\n"
        "이제 너의 공개 발언 차례다. "
        "GM의 직전 발언이 있으면 그것에 대한 반응으로 시작하라. "
        "비공개 채널에서 얻은 정보는 함부로 흘리지 마라. "
        "**1~2문장만**. 짧게. 본문만 출력."
    )


# ---------- User prompt (Night) ----------

def _user_prompt_night(state: GameState, speaker: Unit, channel_id: str) -> str:
    ch = state.channels.get(channel_id)
    if ch is None:
        return "이 채널은 비어있다. 짧게 한마디만."

    visible = state.chat_visible_to(speaker.id)
    transcript = _format_transcript(visible, speaker, state)
    context_hint = _night_context_hint(speaker.role, channel_id)
    gm_block = _last_gm_block(visible, channel_id=channel_id)
    return (
        f"[현재 페이즈]\n{state.phase.value} (Day {state.day})\n"
        f"[지금 발언할 채널]\n{ch.label} — {context_hint}\n\n"
        f"{gm_block}"
        f"[너가 지금까지 보고 들은 모든 대화]\n{transcript or '(아직 없음)'}\n\n"
        "이제 이 채널에서 너의 발언 차례다. "
        "GM의 직전 발언이 있으면 그것에 직접 반응하라. "
        "**1~2문장만**. 짧게. 본문만 출력."
    )


def _last_gm_block(lines: list[ChatLine], *, channel_id: str) -> str:
    """해당 채널에서 GM의 가장 최근 발언을 강조 블록으로 만든다."""
    for ln in reversed(lines):
        if ln.channel_id == channel_id and ln.speaker_kind == "gm":
            return (
                f"[⚠ GM이 방금 한 말 — 반드시 이것에 반응할 것]\n"
                f"{ln.content}\n\n"
            )
    return ""


def _night_context_hint(role: Role, channel_id: str) -> str:
    # 1:1 GM 채널 (밤)
    if channel_id.startswith("private:police"):
        return "GM과의 1:1. 오늘 밤 누구를 조사할지 짧게 말하라."
    if channel_id.startswith("private:doctor"):
        return "GM과의 1:1. 오늘 밤 누구를 보호할지 짧게 말하라."
    if channel_id.startswith("medium:"):
        return "영매와 죽은 자의 대화. 정체를 숨길 필요는 없다."
    # 직업별 단톡 채널 (낮/밤 모두)
    if channel_id == "mafia":
        return (
            "여기는 마피아 단톡이다. 동료 마피아와 GM만 본다. 정체 숨길 필요 없다.\n"
            "**임무**: 오늘 밤 탈락시킬 시민 한 명을 서로 상의해 정한다.\n"
            "**필수 발언 패턴 — 반드시 이 순서로**:\n"
            "1. 동료가 직전에 누구를 지목했는지 그 이름을 먼저 인지하라. (예: '미스트랄이 솔라를 지목했군')\n"
            "2. 그 선택에 동의 또는 반대 입장을 명확히 밝혀라.\n"
            "3. 너의 최종 지목을 한 이름으로 말하라. (동료와 같을 수도, 다를 수도 있음)\n"
            "회피·중립·'모르겠다' 금지. 자기 의견만 반복하지 말고 동료 의견을 반드시 거론하라."
        )
    if channel_id == "police":
        return "경찰 단톡. 같은 직업 + GM만 본다."
    if channel_id == "doctor":
        return "의사 단톡. 같은 직업 + GM만 본다."
    if channel_id == "medium":
        return "영매 단톡. 같은 직업 + GM만 본다."
    if channel_id == "citizen":
        return "시민 단톡. 같은 직업 + GM만 본다. (게임 룰상 시민끼리도 서로 모르는 게 정상이지만, GM이 의도적으로 연 채널이다.)"
    return "비공개 채널."


# ---------- Transcript ----------

def _format_transcript(
    lines: list[ChatLine],
    speaker: Unit,
    state: GameState,
) -> str:
    out = []
    for ln in lines:
        who = ln.speaker_name
        if ln.speaker_kind == "gm":
            who = "[GM]"
        if ln.speaker_id == speaker.id:
            who = f"{who} (나)"
        ch = state.channels.get(ln.channel_id)
        ch_label = ch.label if ch else ln.channel_id
        out.append(f"[{ch_label}] {who}: {ln.content}")
    return "\n".join(out)
