# 05. GameState 런타임 객체

## 왜 만들었나

`models.py`가 데이터 모양이라면, 이건 **하나의 게임 인스턴스가 들고 있는
변이형 상태**다. WebSocket 핸들러가 비대해지지 않게, 모든 상태 변이를
이 클래스 메서드로 모은다.

원칙:
- 모든 상태 변경은 `GameState` 메서드를 통해서만 (직접 필드 변이 금지)
- 페이즈 전환 = 채널 재구성 (낮↔밤이 곧 채널 토폴로지 변경)
- 스냅샷 한 줄(`snapshot()`)로 프론트엔드에 동기화

## 파일

- `backend/game.py`

## RoleConfig

```python
RoleConfig(mafia=2, police=1, doctor=1, medium=1, citizen=2)  # 총 7명
```

GM이 셋업 화면에서 조정. `total()`이 페르소나 수와 일치해야 함.

## 주요 메서드

| 메서드 | 설명 |
|--------|------|
| `setup(personas, role_config)` | 유닛 생성·역할 배정(셔플)·기본 채널(public + 마피아 단톡) 설치 |
| `start_day()` | day++, DAY_DISCUSSION 진입, 투표 초기화, 발언 순서 재구성 |
| `start_voting()` | DAY_VOTING 진입 |
| `start_night()` | NIGHT 진입, 야간 상태 리셋, 능력자 1:1 채널·영매 채널 생성 |
| `record_chat(channel, kind, id, name, content)` | 채팅 1줄 저장 |
| `chat_visible_to(unit_id)` | 해당 유닛이 멤버인 모든 채널의 발언 시간순 — **LLM 컨텍스트 빌드용** |
| `current_speaker()` / `advance_speaker()` | 라운드 로빈 |
| `round_complete()` | 한 바퀴 돌았는지 |
| `kill_unit(uid)` | 사망 처리 + 모든 채널 멤버/발언순서에서 제거 |
| `record_vote(voter, target, raw)` | 투표 기록 (동일 voter 덮어쓰기) |
| `tally()` | `{target_id: 표수}` |
| `winner()` | 마피아 == 시민 진영 이상 → 마피아 승, 마피아 0 → 시민 승 |
| `snapshot()` | `GameSnapshot` 반환 |

## 채널 ID 컨벤션

| ID 패턴 | 종류 |
|---------|------|
| `public` | 낮 공개 |
| `mafia` | 마피아 단톡 |
| `private:{role}:{unit_id}` | 능력자 1:1 GM |
| `medium:{medium_id}:{day}` | 영매 ↔ 죽은 자 (날짜별로 새로 열림) |

## 정보 가시성 (영매 룰 핵심)

`chat_visible_to(unit_id)`는 **그 유닛이 채널 멤버인 발언만** 반환.
- 살아있는 영매는 `medium:...` 채널의 멤버
- 죽은 유닛은 어느 채널 멤버도 아님 → 보통은 컨텍스트 없음
- 단, 영매가 죽은 유닛을 호출할 때 GM이 동적으로 그 죽은 유닛을 `medium:...` 채널 멤버로 추가하는 식으로 처리 (다음 밤 페이즈 작업에서 구현)

## 승리 조건

표준 마피아 룰:
- 마피아 ≥ 비-마피아 → 마피아 승
- 마피아 0 → 시민 진영 승
- 그 외 → 진행

## 다음 단계

- `06_websocket.md`: GM ↔ 서버 메시지 프로토콜 + 핸들러
