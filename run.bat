@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found. Run setup.bat first.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo Checking Ollama (http://localhost:11434)...
curl -s -o nul -w "%%{http_code}" http://localhost:11434 2>nul | findstr "200" >nul
if errorlevel 1 (
    echo [WARN] Ollama is not responding. Make sure it is running.
    echo        See: https://ollama.com
    echo.
)

echo Starting AI Mafia server -- http://localhost:8000
echo (Stop: Ctrl+C)
echo.

start "" http://localhost:8000

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

pause
