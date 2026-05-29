@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
title WARFRAME-RELIC [Dev Mode]

echo.
echo ================================================
echo       WARFRAME-RELIC - 开发模式
echo ================================================
echo.

rem --- 找到 Python ---
set PYTHON_CMD=
if exist "venv\Scripts\python.exe" (
    set PYTHON_CMD=venv\Scripts\python.exe
) else (
    echo [错误] 未找到虚拟环境！请先运行 SETUP.bat 初始化环境。
    echo.
    pause
    exit /b 1
)

rem --- 启动 dev_runner ---
echo [*] 自动重启模式 (文件变更时自动重载)
echo [*] 按 Ctrl+C 退出
echo [*] 崩溃日志: crash_log.txt
echo.
echo ================================================
echo.

!PYTHON_CMD! dev_runner.py

echo.
echo 开发模式已退出。
pause
