@echo off
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
    cls
    echo ==========================================
    echo   Video Join Tool v1.2.1
    echo ==========================================
    echo.
    echo [ERROR] Python is required
    echo Download: python.org/downloads/
    echo.
    pause
    exit /b 1
)
python video-join-v12.py
pause
