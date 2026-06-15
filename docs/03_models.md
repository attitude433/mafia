# 03. 게임 데이터 모델

## 왜 만들었나

게임 상태의 "모양"을 한 곳에 모은다. 런타임 변이는 다음 단계(`game.py`)에서
처리하고, 여기서는 **타입**과 **WebSocket으로 직렬화 가능한 형태**만 정의한다.

이렇게 분리하면:
- 프론트엔드 메시지 스키마가 곧 Pydantic 모델 → 추적 쉬움
- 게임 로직(Python)과 프론트엔드(JS) 사이의 계약이 명시적

## 파일

- `backend/models.py`

## 모델 개요

| 모델 | 역할 |
|------|------|
| `Role` enum | 마피아/경찰/의사/영매/시민 |
| `Phase` enum | setup / day_discussion / day_voting / night / ended |
| `ChannelKind` enum | public / mafia / private / medium |
| `Persona` | 이름 + 한 줄 요약 + 말투 + 기벽 (시스템 프롬프트 재료) |
| `NightState` | 밤마다 리셋되는 유닛별 표식 (살해 타겟, 보호, 조사) |
| `Unit` | id + persona + role + alive + night |
| `ChatLine` | 단일 발언 (채널 + 화자 + 본문 + 타임스탬프) |
| `Channel` | 채팅방 인스턴스 (kind + label + 멤버 unit ids) |
| `Vote` | 유닛의 투표 (target_id None = 기권/파싱실패, raw 보존) |
| `GameSnapshot` | 프론트 동기화용 단일 페이로드 |

## 채널 모델 설명

게임 내 모든 대화는 **채널**로 추상화된다. 같은 추상으로 다 처리:

- 낮 공개 채팅: `kind=PUBLIC`, 멤버 = 살아있는 전원
- 마피아 단톡: `kind=MAFIA`, 멤버 = 살아있는 마피아 전원 (GM은 묵시적 포함)
- 경찰 ↔ GM: `kind=PRIVATE`, 멤버 = [경찰 유닛]
- 의사 ↔ GM: `kind=PRIVATE`, 멤버 = [의사 유닛]
- 영매 ↔ 죽은 유닛 ↔ GM: `kind=MEDIUM`, 멤버 = [영매 유닛, 대화 대상 죽은 유닛]

채널은 페이즈 진입 시 동적으로 생성/재활성화된다.

## 다음 단계

- `04_persona.md`: 자동 생성 + 수동 입력 페르소나 시스템
- 이어서 `game.py`에서 GameState 런타임 객체 구현
