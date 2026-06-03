@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"
echo ================================================
echo WM Item Search - Price Query Test Module
echo ================================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found in PATH
    pause
    exit /b 1
)

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" wm_search.py
) else (
    python wm_search.py
)

echo.
echo ================================================
echo Program exited
echo ================================================
pause