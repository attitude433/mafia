# 09. 밤 페이즈 (마피아 단톡 + 1:1 + 영매)

## 왜 만들었나

낮과 달리 밤은 라운드 로빈이 아닌 **GM이 채널·발언자를 명시적으로 골라
진행**한다. 그래서 `next_speaker` 대신 `speak_in_channel`과 `speak_dead`
를 추가했다.

## 파일

- `backend/protocol.py` — `SpeakInChannelMsg`, `SpeakDeadMsg` 추가
- `backend/engine.py` — `on_speak_in_channel`, `on_speak_dead` 핸들러
- `backend/phases.py` — `speak_unit_in_channel`, `speak_dead_in_medium` (이미 task 07에서 같이 작성)
- `backend/prompts.py` — `build_night_messages`, `_night_context_hint` (task 07에서 같이 작성)

## 채널과 발언 매트릭스

| 채널 ID | 멤버 | 발언 가능 |
|---------|------|-----------|
| `mafia` | 살아있는 마피아 전원 | 각 마피아가 차례로 발언, GM은 `gm_say` |
| `private:police:{id}` | 경찰 1명 | 경찰 발언, GM 질문 |
| `private:doctor:{id}` | 의사 1명 | 의사 발언, GM 질문 |
| `medium:{medium_id}:{day}` | 영매 1명 (+ 호출된 죽은 자) | 영매 발언 + 죽은 자 발언 |

## GM 진행 시나리오

### 마피아 단톡
```
GM: { type: "set_active_channel", channel_id: "mafia" }
GM: { type: "gm_say", channel_id: "mafia", content: "오늘 누구 죽일까?" }
GM: { type: "speak_in_channel", unit_id: <mafia_1>, channel_id: "mafia" }
GM: { type: "speak_in_channel", unit_id: <mafia_2>, channel_id: "mafia" }
# 합의 보이면
GM: { type: "set_night_flag", unit_id: <target>, flag: "targeted_by_mafia", value: true }
```

### 경찰 조사
```
GM: { type: "speak_in_channel", unit_id: <police>, channel_id: "private:police:..." }
# 경찰이 "○○를 조사하겠습니다" 비슷한 발언 → GM이 읽고 결정
GM: { type: "set_night_flag", unit_id: <target>, flag: "investigated_by_police", value: true }
GM: { type: "gm_say", channel_id: "private:police:...", content: "결과: 마피아 아님" }
```

### 영매 + 죽은 자
```
GM: { type: "summon_dead", medium_channel_id: "medium:...", dead_unit_id: <ghost> }
# 죽은 자가 채널 멤버로 추가됨 → 페르소나/대화 가시
GM: { type: "speak_in_channel", unit_id: <medium>, channel_id: "medium:..." }
GM: { type: "speak_dead", dead_unit_id: <ghost>, medium_channel_id: "medium:..." }
```

### 결과 적용
```
GM: { type: "apply_night" }
# targeted_by_mafia && !protected_by_doctor → 사망
# 자동으로 winner() 체크, 결판나면 game.phase = ENDED
GM: { type: "start_day" }   # 다음 낮으로
```

## 프롬프트 차이 (낮 vs 밤)

`build_night_messages`는 system 프롬프트는 동일(`_system_prompt`), user 프롬프트만
`_user_prompt_night`로 바꿔 **해당 채널의 히스토리만** 보여준다. 페르소나는 그대로,
정체는 드러내도 됨(같은 진영/GM 1:1이라).

`_night_context_hint`가 채널 종류에 따라 행동 지침을 다르게 줌
("의논해라" / "조사 대상 말하라" / "보호 대상 말하라" / "죽은 자와 이야기").

## 죽은 자의 발언

`speak_dead_in_medium` — 페르소나는 살아있을 때와 동일하게 사용. 단지 `speaker_name`을
`{name}(死)`로 표시해 GM·영매가 구분할 수 있게 한다. 죽은 자 입장에선 죽기 전까지의
공개 채팅 + 영매 채널 본인 발언만 컨텍스트 (다른 비공개 채널 멤버는 아니었으므로).

## 다음 단계

- task 6: 프론트엔드 — 채팅 UI + GM 사이드바 패널
