# AI Mafia

Ollama + Gemma 4 12B로 구동하는 채팅 기반 마피아 게임.
GM(사람) 한 명이 모든 페이즈 전환을 통제하고, 단일 LLM 인스턴스가
페르소나별로 번갈아 호출되어 각 유닛(AI 플레이어)을 연기합니다.

## 실행 (Windows)

처음 한 번:
```
setup.bat
```

이후 실행:
```
run.bat
```

`run.bat`이 자동으로 브라우저(http://localhost:8000)를 열어줍니다.
종료는 콘솔에서 `Ctrl+C`.

### 수동 실행

```bash
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### Ollama 모델 태그가 다를 경우

```
set OLLAMA_MODEL=실제_태그명
run.bat
```

## 진행 문서

작업 단위별 설계/구현 노트는 [docs/](./docs/)를 참조.

- [01. 프로젝트 스켈레톤](./docs/01_skeleton.md)
- [02. Ollama 클라이언트](./docs/02_ollama_client.md)
- [03. 게임 데이터 모델](./docs/03_models.md)
- [04. 페르소나 시스템](./docs/04_persona.md)
- [05. GameState 런타임](./docs/05_game_state.md)
- [06. WebSocket 프로토콜 + 엔진](./docs/06_websocket.md)
- [07. 낮 페이즈 + 투표](./docs/07_day_phase.md)
- [09. 밤 페이즈](./docs/09_night_phase.md)
- [06b. 프론트엔드](./docs/06b_frontend.md)
- [📦 사용 모델 + pull 명령](./docs/MODELS.md)
