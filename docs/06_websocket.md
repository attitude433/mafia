# 06. WebSocket 프로토콜 + 엔진

## 왜 만들었나

GM 브라우저 ↔ 서버 간 **단일 양방향 채널**로 모든 게임 인터랙션을 처리.
HTTP REST 없이 WebSocket 하나로:
- GM이 모든 명령(셋업, 페이즈 전환, 발언 트리거, 유닛 사망 처리 등)을 보냄
- 서버가 스냅샷·채팅 라인·LLM 스트리밍 토큰을 push

## 파일

- `backend/protocol.py` — 메시지 타입 (Pydantic discriminated union)
- `backend/engine.py` — `GameEngine`: 핸들러 디스패치 + 상태 변이 + 스냅샷 푸시
- `backend/phases.py` — 페이즈별 LLM 오케스트레이션 (현재는 stub, 7~9에서 채움)
- `backend/main.py` — `/ws` 엔드포인트

## 메시지 (GM → 서버)

| type | 페이로드 | 설명 |
|------|---------|------|
| `setup` | `persona_mode`, `count`, `role_config`, `personas?`, `theme?` | 게임 셋업 |
| `start_day` | – | 다음 낮 진입 |
| `start_voting` | – | 토론 → 투표 |
| `start_night` | – | 밤 진입 |
| `next_speaker` | – | 라운드 로빈 한 칸 (현재 발언자가 LLM 발언) |
| `gm_say` | `channel_id`, `content` | GM이 채널에 직접 메시지 |
| `set_active_channel` | `channel_id` | GM UI 포커스 변경 (멤버 가시성과 무관) |
| `kill_unit` | `unit_id` | 즉시 사망 처리 (보통은 `apply_night` 사용) |
| `set_night_flag` | `unit_id`, `flag`, `value` | 유닛 상태 패널 토글 |
| `apply_night` | – | targeted - protected = 사망 |
| `summon_dead` | `medium_channel_id`, `dead_unit_id` | 영매가 죽은 자 호출 |
| `end_game` | – | 게임 종료 |
| `request_snapshot` | – | 전체 상태 재전송 |

## 메시지 (서버 → GM)

| type | 페이로드 | 설명 |
|------|---------|------|
| `snapshot` | `data: GameSnapshot` | 전체 상태 |
| `chat` | `line: ChatLine` | 단발 발언 (GM 또는 비스트리밍) |
| `stream_start` | `channel_id`, `speaker_name`, `speaker_id` | LLM 스트림 시작 |
| `stream_delta` | `channel_id`, `delta` | LLM 토큰 조각 |
| `stream_end` | `channel_id`, `line: ChatLine` | LLM 스트림 완료, 확정 라인 |
| `tally` | `tally: {target_id: count}` | 투표 집계 |
| `info` | `message` | GM에게 알림 (셋업 완료, 사망 보고 등) |
| `error` | `message` | 잘못된 명령 / 처리 실패 |

## 핸들러 패턴

```python
class GameEngine:
    async def handle(raw): ...  # parse → dispatch on type → on_xxx
    async def on_setup(msg): ...
    async def on_start_day(msg): ...
    async def on_next_speaker(msg): from .phases import speak_current_unit; ...
```

`on_xxx` 컨벤션 — 새 메시지 추가 시 핸들러 메서드 한 개만 추가.

## 현재 stub

`phases.speak_current_unit()`은 자리표시자 문자열을 발언한다.
실제 LLM 발언은 task 07(낮)에서 구현. 컨텍스트 빌딩 / 스트리밍 / 투표 파싱이 거기로 들어감.

## 다음 단계

- `07_day_phase.md`: 라운드 로빈 LLM 발언 + 컨텍스트 빌드 + 스트리밍
