@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
title 打包 WARFRAME-RELIC

echo.
echo ============================================================
echo           WARFRAME-RELIC - 打包
echo ============================================================
echo.

rem ==========================================
rem Check Python venv
rem ==========================================
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found!
    echo Please run WARFRAME-RELIC.bat first to initialize.
    pause
    exit /b 1
)

rem ==========================================
rem Run Python build script with progress
rem ==========================================
echo [INFO] Starting build process...
echo.
venv\Scripts\python.exe build_exe.py

if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Build process failed! See output above.
    pause
    exit /b 1
)

endlocal
