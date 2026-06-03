@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
title WARFRAME-RELIC 环境初始化

echo.
echo ============================================================
echo       WARFRAME-RELIC - 零基础环境初始化
echo ============================================================
echo.

rem ==========================================
rem 0. 检查 Python
rem ==========================================
echo [0/4] 检测 Python...

set PYTHON_CMD=
set PYTHON_VER=

:: 优先使用 py launcher
where py >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=2" %%v in ('py -3 --version 2^>^&1') do set PYTHON_VER=%%v
    if defined PYTHON_VER (
        set "PYTHON_CMD=py -3"
        echo   [OK] 找到 Python !PYTHON_VER! ^(通过 py launcher^)
    )
)

:: 如果 py launcher 没找到，尝试 python
if not defined PYTHON_CMD (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYTHON_VER=%%v
        set "PYTHON_CMD=python"
        echo   [OK] 找到 Python !PYTHON_VER! ^(通过 PATH^)
    )
)

:: 尝试 python3
if not defined PYTHON_CMD (
    where python3 >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=2" %%v in ('python3 --version 2^>^&1') do set PYTHON_VER=%%v
        set "PYTHON_CMD=python3"
        echo   [OK] 找到 Python !PYTHON_VER! ^(通过 PATH^)
    )
)

:: 都没找到
if not defined PYTHON_CMD (
    echo   [ERROR] 未找到 Python!
    echo.
    echo   请先安装 Python 3.10+
    echo   下载地址: https://www.python.org/downloads/
    echo   【重要】安装时务必勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

echo.

rem ==========================================
rem 1. 创建虚拟环境
rem ==========================================
echo [1/4] 创建虚拟环境 (venv)...

if exist "venv\Scripts\python.exe" (
    echo   [SKIP] 虚拟环境已存在
) else (
    %PYTHON_CMD% -m venv venv
    if !errorlevel! neq 0 (
        echo   [ERROR] 虚拟环境创建失败!
        pause
        exit /b 1
    )
    echo   [OK] 虚拟环境创建成功
)

echo.

rem ==========================================
rem 2. 升级 pip
rem ==========================================
echo [2/4] 升级 pip...

venv\Scripts\python.exe -m pip install --upgrade pip -i https://mirrors.cloud.tencent.com/pypi/simple --quiet
if %errorlevel% neq 0 (
    echo   [WARN] pip 升级失败，尝试继续...
) else (
    echo   [OK] pip 已是最新
)

echo.

rem ==========================================
rem 3. 安装项目依赖
rem ==========================================
echo [3/4] 安装项目依赖...
echo   (优先使用腾讯云镜像，失败则回退到官方源)
echo.

venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.cloud.tencent.com/pypi/simple
if %errorlevel% neq 0 (
    echo.
    echo   [WARN] 腾讯云镜像失败，尝试官方源...
    echo.
    venv\Scripts\python.exe -m pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo.
        echo   [ERROR] 依赖安装失败!
        echo   请检查网络连接后重试。
        echo.
        pause
        exit /b 1
    )
)

echo.
echo   [OK] 依赖安装完成

echo.

rem ==========================================
rem 4. 验证环境
rem ==========================================
echo [4/4] 验证环境...

echo.
echo   检查关键模块...

set ALL_OK=1

for %%m in (PyQt6 dxcam keyboard rapidocr_onnxruntime cv2 PIL numpy pypinyin) do (
    venv\Scripts\python.exe -c "import %%m" >nul 2>&1
    if !errorlevel! equ 0 (
        echo     [+] %%m
    ) else (
        echo     [-] %%m - 缺失!
        set ALL_OK=0
    )
)

echo.

if %ALL_OK% equ 0 (
    echo   [WARN] 部分模块缺失，可能需要手动安装
) else (
    echo   [OK] 所有模块验证通过!
)

echo.

rem ==========================================
rem 完成
rem ==========================================
echo ============================================================
echo       环境初始化完成!
echo ============================================================
echo.
echo   启动方式:
echo     1. 开发模式 (推荐): 双击 DEV_RUN.bat
echo     2. 直接启动:       双击 WARFRAME-RELIC.bat
echo     3. 命令行启动:     venv\Scripts\python.exe main.py
echo.
echo   打包发布:
echo     双击 打包.bat
echo.
echo ============================================================

pause
endlocal
