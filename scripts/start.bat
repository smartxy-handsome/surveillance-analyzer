@echo off
echo Building frontend...
cd /d "%~dp0\..\frontend"
call npm run build
if errorlevel 1 (
    echo Frontend build failed!
    pause
    exit /b 1
)
cd /d "%~dp0\.."
echo Starting server...
uv run python -m src.main
