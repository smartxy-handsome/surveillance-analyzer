@echo off
setlocal
cd /d "%~dp0\.."

echo Building frontend...
cd /d "%~dp0\..\frontend"
call npm run build
if errorlevel 1 (
    echo.
    echo [ERROR] Frontend build failed. See message above.
    pause
    exit /b 1
)
cd /d "%~dp0\.."

where uv >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] "uv" not found in PATH.
    echo Install it from https://docs.astral.sh/uv/ then reopen this script.
    pause
    exit /b 1
)

netstat -ano | findstr ":8000" | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
    echo.
    echo [ERROR] Port 8000 is already in use - the analyzer may already be running.
    echo Close the other instance first, or start on another port:
    echo     uv run python -m src.main --port 8001
    pause
    exit /b 1
)

echo Starting server on http://127.0.0.1:8000 ...
uv run python -m src.main
set EXITCODE=%errorlevel%
echo.
echo [INFO] Server exited (code %EXITCODE%). If this was unexpected,
echo        read the error message above and report it.
pause
exit /b %EXITCODE%
