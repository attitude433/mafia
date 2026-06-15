# 07. 낮 페이즈 (라운드 로빈 LLM 발언)

## 왜 만들었나

stub이던 `speak_current_unit`을 실제 LLM 호출로 교체. 페르소나·역할·페이즈에
맞는 시스템 프롬프트를 만들고, Gemma에서 토큰을 스트리밍 받아 WebSocket으로
GM 화면에 흘려보낸다.

## 파일

- `backend/prompts.py` — 시스템 프롬프트 + 사용자 프롬프트(대화 트랜스크립트) 빌더
- `backend/phases.py` — 스트리밍 루틴 + 페이즈 라우팅 + 투표 파싱 진입점

## 발언 흐름 (GM → 서버)

```
GM: { type: "next_speaker" }
  → engine.on_next_speaker()
  → phases.speak_current_unit()
    → prompts.build_day_messages(state, speaker)
    → llm.chat_stream(messages)
      → send stream_start
      → send stream_delta × N
      → send stream_end (final ChatLine)
    → state.advance_speaker()
    → send snapshot
```

## 시스템 프롬프트 구성

```
너는 마피아 게임 참가자다. 페르소나에 충실하게, 짧게 발언하라.
[너의 페르소나]
- 이름 / 소개 / 말투 / 습관
[너의 비밀 역할]
- 마피아 → 동료 마피아 이름 명시
- 경찰/의사/영매/시민 → 능력 요약
[참가자]
- 살아있음/사망 명시
```

페이즈별 사용자 프롬프트:
- **DAY_DISCUSSION**: 공개 채팅 트랜스크립트 + "지금은 낮 토론 시간"
- **DAY_VOTING**: 위 + "마지막 문장은 정확히 '○○를 투표합니다.' 로 끝내라"

## 투표 파싱

투표 페이즈 발언에서 정규식 `([\w가-힣]+)\s*를?\s*투표` 로 후보를 추출,
가장 마지막 매치를 우선으로 `unit_by_name()`에 매칭 (정확 이름 → 부분 이름 → fail).
실패 시 `Vote(target_id=None)`로 기록(기권 처리).

집계는 `state.tally()` 그대로 사용 — 발언 직후 매번 GM에게 `tally` 메시지 푸시.

## 정보 가시성

이 단계의 Day 발언은 공개 채팅만 본다 (`state.chat["public"]`).
밤에 본 비공개 정보(마피아 단톡, 1:1)는 트랜스크립트에 포함되지 않음 — 살아있는
유닛이 다른 채널 멤버라도 Day 프롬프트는 public만 잘라 보여줌으로써 메타 누출 방지.

(밤 페이즈 발언 시에는 `build_night_messages`가 그 채널 한 개의 히스토리만 보임)

## 스트리밍 메시지

| 단계 | 메시지 |
|------|--------|
| 시작 | `{type: "stream_start", channel_id, speaker_id, speaker_name}` |
| 진행 | `{type: "stream_delta", channel_id, delta}` (반복) |
| 종료 | `{type: "stream_end", channel_id, line: ChatLine}` |

프론트엔드는 stream_start에서 빈 말풍선 만들고, delta로 텍스트 추가, stream_end에서 확정.

## 다음 단계

- `08_voting.md`: 사실상 본 작업에 포함됨. 다음 작업은 밤 페이즈(`09_night.md`).
