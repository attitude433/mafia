# 02. Ollama 클라이언트 래퍼

## 왜 만들었나

게임 로직 어디서도 Ollama HTTP를 직접 두드리지 않게 하기 위해, 단일 진입점인
`OllamaClient`를 둔다. 페르소나 시스템 프롬프트 주입, 스트리밍, 타임아웃,
에러 변환을 한 곳에서 처리한다.

이후 모든 유닛 발언/페르소나 생성/투표 발언은 이 클라이언트를 통한다.

## 모델

- 기본: `gemma4:12b` (Ollama 로컬, 사용자 환경에 이미 설치됨)
- `OLLAMA_MODEL`, `OLLAMA_URL` 환경변수로 오버라이드 가능

## 파일

- `backend/llm.py`

## API

```python
client = OllamaClient()  # base_url/model은 env 또는 인자로

# 단발 호출
text = await client.chat([
    ChatMessage("system", "너는 마피아다..."),
    ChatMessage("user", "지금 발언해라"),
])

# 스트리밍 호출 — 토큰 들어오는 대로 WebSocket으로 흘려보낼 때 사용
async for delta in client.chat_stream(messages):
    await ws.send_text(delta)

await client.aclose()
```

### 메시지 모델

`ChatMessage(role, content)` — role은 `system | user | assistant`.

게임 컨텍스트에서:
- `system`: 페르소나 + 역할 + 현재 페이즈 + 규칙
- `user`: GM의 지시 / 다른 유닛들의 발언 기록
- `assistant`: 해당 유닛 자신의 과거 발언

### 옵션

`chat()` / `chat_stream()` 공통:
- `temperature` (기본 0.8) — 유닛 개성을 살리기 위해 약간 높게
- `top_p` (기본 0.9)
- `stop` — 라운드 로빈 발언 길이 제어용

### 에러

Ollama 응답 실패 / 빈 응답 → `OllamaError` 로 통일.

## 다음 단계

- `03_models.md`: Unit, Role, Phase, Channel 데이터 모델
