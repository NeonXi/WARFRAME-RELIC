@echo off
setlocal enabledelayedexpansion

chcp 437 >nul 2>&1
cd /d "%~dp0"
title WARFRAME-RELIC

echo.
echo ================================================
echo       WARFRAME-RELIC Launcher
echo ================================================
echo.

set "LOG_FILE=launch_log.txt"
echo %date% %time% - Starting WARFRAME-RELIC > "%LOG_FILE%"

rem --- Step 1: Find Python ---
set PYTHON_CMD=python
set "VENV_PYTHON=python"

if exist "venv\Scripts\python.exe" (
    set "VENV_PYTHON=venv\Scripts\python.exe"
    echo [OK] Found venv Python
) else (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        echo [OK] Using system Python
    ) else (
        echo [ERROR] Python not found!
        echo %date% %time% - ERROR: Python not found >> "%LOG_FILE%"
        pause
        exit /b 1
    )
)

rem --- Step 2: Start program ---
echo Starting WARFRAME-RELIC...
echo %date% %time% - Starting main.py >> "%LOG_FILE%"
echo.

!VENV_PYTHON! main.py

if !errorlevel! neq 0 (
    echo.
    echo ==============================================
    echo   Program exited with error: !errorlevel!
    echo ==============================================
    echo %date% %time% - ERROR: Exit code !errorlevel! >> "%LOG_FILE%"
    pause
)

endlocal