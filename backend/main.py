from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import httpx
import os

from .engine import GameEngine
from .llm import OllamaClient

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="AI Mafia")

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# 기본 LLM은 Ollama. 셋업에서 Anthropic으로 교체될 수 있음.
_llm = OllamaClient()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/ollama/models")
async def ollama_models() -> dict:
    base = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5.0) as cli:
            r = await cli.get(f"{base}/api/tags")
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "models": []}
    models = [
        {"name": m.get("name", ""), "size": m.get("size", 0)}
        for m in data.get("models", [])
        if m.get("name")
    ]
    return {"ok": True, "models": models}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()

    async def send(msg: dict) -> None:
        await ws.send_json(msg)

    engine = GameEngine(send=send, llm=_llm)
    try:
        while True:
            data = await ws.receive_json()
            await engine.handle(data)
    except WebSocketDisconnect:
        return


@app.on_event("shutdown")
async def _shutdown() -> None:
    await _llm.aclose()
