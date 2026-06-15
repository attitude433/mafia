# 06b. 프론트엔드 (채팅 + GM 패널)

## 왜 만들었나

GM 한 명이 이 게임의 유일한 인간 사용자. 그래서 UI는 GM 시점 단일 화면:
- 셋업 화면(역할 구성, 페르소나 모드)
- 게임 화면(채널 탭, 채팅, 유닛 상태 사이드바, 페이즈 컨트롤)

빌드 도구·프레임워크 없이 순수 HTML/CSS/JS — 작은 코드량으로 충분.

## 파일

- `frontend/index.html` — 셋업 뷰 + 게임 뷰 (둘 다 같은 페이지)
- `frontend/style.css` — 다크 테마
- `frontend/views.js` — DOM 렌더 헬퍼 (`UI.*`)
- `frontend/app.js` — WebSocket + 상태 + 디스패치

## 게임 화면 레이아웃

```
┌─────────────────────────────────────────────────┐
│ phase-bar:  [SETUP] Day 0  ... [낮][투표][밤]   │
├──────────────────────────────────┬──────────────┤
│  채널 탭 | 공개 | 마피아 | 경찰...│              │
│  ┌────────────────────────────┐  │  유닛 카드   │
│  │       채팅 메시지들        │  │  - 김상철    │
│  │       (스트리밍 토큰)      │  │   [표적][..] │
│  └────────────────────────────┘  │  - 박지수    │
│  [GM 입력  ............ 보내기 ] │  ...         │
├──────────────────────────────────┴──────────────┤
│ tally-bar: 김상철 2표  박지수 1표               │
└─────────────────────────────────────────────────┘
```

## 메시지 흐름

- 진입 시 셋업 폼만 표시
- "게임 시작" 클릭 → WebSocket open → `setup` 메시지 → 서버가 snapshot 응답
- snapshot에서 phase가 `setup`이 아니면 게임 뷰로 전환
- 이후 WebSocket 메시지(chat / stream_* / snapshot / tally / info / error)를 dispatch

### 스트리밍 처리

```
stream_start → 비어있는 .msg.streaming 말풍선 생성, 노드 보관
stream_delta → 노드.appendChild(textNode(delta))
stream_end   → 노드.classList.remove("streaming"), 노드 핸들 해제
```

채널 전환 시 스트림 중이면 자동 무시 (활성 채널 외엔 토큰 받지 않음).

## 유닛 카드 액션

| 액션 | 송신 메시지 |
|------|-------------|
| `[표적]` 칩 | `set_night_flag` (flag = `targeted_by_mafia`) |
| `[보호]` 칩 | `set_night_flag` (flag = `protected_by_doctor`) |
| `[조사]` 칩 | `set_night_flag` (flag = `investigated_by_police`) |
| `즉시 사망` 버튼 | `kill_unit` |
| `이 채널서 발언` 버튼 | `speak_in_channel` |
| `영매 호출` 버튼(죽은 유닛) | `summon_dead` + `speak_dead` |

## 셋업 폼

- **역할 구성**: 마피아/경찰/의사/영매/시민 카운트 (자동 합산)
- **페르소나 모드**:
  - 자동: 분위기 텍스트(선택) → 서버가 Gemma로 N명 생성
  - 수동: `이름 | 소개 | 말투 | 습관` 한 줄씩 입력, 줄 수 = 총원

## 알려진 한계

- 스냅샷에 채팅 라인을 싣지 않음 → 채널 전환 시 과거 채팅을 다시 못 봄.
  (필요해지면 서버 스냅샷에 `chat` 포함 또는 `chat_history` 요청 추가)
- 단일 GM 가정 — 여러 탭으로 열면 별개 게임이 됨.
- 모바일 대응 X.

## 실행

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload
# → http://localhost:8000
```

Ollama는 기본 `http://localhost:11434`로 가정. 모델 다른 이름이면
`OLLAMA_MODEL=네_태그명 uvicorn ...`.

## 다음 단계

- 통합 테스트 (전체 한 판 돌려보기)
- 채팅 히스토리 영속화
- 채널별 가시 토글로 사이드바에서 빠른 전환
