# 01. 프로젝트 스켈레톤

## 왜 만들었나

이후 모든 기능(WebSocket, Ollama 호출, 채팅 UI, GM 패널)을 얹을 수 있는
최소한의 FastAPI + 정적 프론트엔드 골격을 먼저 세운다.
이 단계에서는 게임 로직은 없고, "서버가 뜨고 정적 자산이 서빙된다"만 보장한다.

## 스택

- **백엔드**: Python 3.11+, FastAPI, Uvicorn
- **HTTP 클라이언트**: httpx (다음 단계에서 Ollama 호출용)
- **모델 검증**: Pydantic v2
- **프론트엔드**: 순수 HTML/CSS/JS (빌드 도구 없음)

## 파일 구조

```
mafia/
├── backend/
│   ├── __init__.py
│   └── main.py          # FastAPI 앱, 정적 파일 서빙, /health
├── frontend/
│   ├── index.html       # 진입 페이지 (이후 채팅 UI 확장)
│   ├── style.css
│   └── app.js
├── docs/
│   └── 01_skeleton.md   # 본 문서
├── requirements.txt
└── README.md
```

## API

| 메서드 | 경로       | 설명                              |
|--------|-----------|-----------------------------------|
| GET    | `/`       | `frontend/index.html` 반환        |
| GET    | `/static/*` | 프론트엔드 정적 자산              |
| GET    | `/health` | `{"status": "ok"}` (가동 확인)    |

## 실행 확인

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload
# http://localhost:8000  → 스켈레톤 페이지
# http://localhost:8000/health → {"status":"ok"}
```

## 다음 단계

- `02_ollama_client.md`: Ollama HTTP API 래퍼 (gemma4:12b 호출, 스트리밍, 페르소나 시스템 프롬프트 주입)
