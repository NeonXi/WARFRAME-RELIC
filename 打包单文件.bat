@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
title 单文件EXE打包 - WARFRAME-RELIC

echo.
echo ============================================================
echo     WARFRAME-RELIC - 单文件 EXE 打包
echo ============================================================
echo.
echo  生成产物: dist\WARFRAME-RELIC.exe (单个文件)
echo  优点: 一个文件分发方便
echo  缺点: 首次启动较慢 (10-15秒解压)
echo.
echo ============================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境!
    echo 请先运行 SETUP.bat 初始化。
    pause
    exit /b 1
)

echo [*] 开始打包...
echo.
venv\Scripts\python.exe build_onefile.py

if !errorlevel! neq 0 (
    echo.
    echo [失败] 打包过程出错!
    pause
    exit /b 1
)

endlocal
