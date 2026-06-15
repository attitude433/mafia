@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Locating real Python (skipping Microsoft Store stub)...
set "PY="

rem 1) py launcher (recommended)
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PY=py -3"
    echo Using: py -3
    goto :py_found
)

rem 2) Iterate through `where python` and skip WindowsApps stub
for /f "delims=" %%P in ('where python 2^>nul') do (
    echo %%P | findstr /i "WindowsApps" >nul
    if errorlevel 1 (
        rem real python
        "%%P" --version >nul 2>&1
        if not errorlevel 1 (
            set "PY=%%P"
            echo Using: %%P
            goto :py_found
        )
    )
)

echo.
echo [ERROR] No usable Python found.
echo The Microsoft Store stub does not work for venv.
echo Install Python from https://www.python.org/downloads/ (check "Add to PATH").
pause
exit /b 1

:py_found
echo.

echo [2/3] Creating virtualenv (.venv)...
if exist ".venv" (
    echo Removing existing .venv...
    rmdir /s /q ".venv"
)

%PY% -m venv .venv
if errorlevel 1 (
    echo [ERROR] venv creation failed even with %PY%.
    pause
    exit /b 1
)
echo venv created.
echo.

echo [3/3] Installing dependencies...
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

echo.
echo Setup complete. Double-click run.bat to start the server.
pause
