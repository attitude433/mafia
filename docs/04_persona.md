# 04. 페르소나 시스템 (자동/수동)

## 왜 만들었나

유닛의 "캐릭터 시트"를 만드는 두 경로를 한 모듈에서 책임진다.

- **자동**: Gemma에게 N명을 한 번에 만들도록 요청 (JSON 모드)
- **수동**: GM이 직접 이름/말투를 입력
- **안전망**: Ollama 실패 시 fallback 풀에서 즉시 채움

역할(Role) 배정은 여기서 하지 않는다. 그건 `game.py`의 setup 단계.

## 파일

- `backend/persona.py`
- `backend/llm.py` — `chat(..., json_mode=True)` 추가 (Ollama `format: json` 옵션)

## API

```python
# 자동 생성
personas = await generate_personas(client, count=6, theme="조용한 시골 마을")

# 수동 입력 (셋업 UI에서 한 명씩)
p = manual_persona(name="김상철", summary="50대 택시기사", style="짧고 퉁명스러움")

# 폴백 (Ollama 불통 / JSON 파싱 실패 시)
personas = fallback_personas(count=6)
```

## 자동 생성 프롬프트

시스템 프롬프트에서 명시적 JSON 스키마를 강제:

```json
{"personas": [{"name": "...", "summary": "...", "style": "...", "quirks": "..."}]}
```

`temperature=1.0`으로 개성 다양화. Ollama `format: "json"` 옵션으로 비-JSON 출력 차단.

## 에러/실패 처리

- 비-JSON 응답 → `ValueError`
- `personas` 키 누락/빈 리스트 → `ValueError`
- Ollama HTTP 실패 → `OllamaError` (호출자가 잡고 `fallback_personas()` 호출)

이름 중복 시 자동으로 `이름2`, `이름3` 접미사.

## 다음 단계

- `05_game_state.md`: `game.py`에 GameState 런타임 객체 — 유닛/페이즈/채널을 합쳐서 게임 진행을 들고 있는 객체. 페르소나 + 역할 배정도 여기서.
