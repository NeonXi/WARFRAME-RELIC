@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
title WARFRAME-RELIC

echo.
echo ================================================
echo       WARFRAME-RELIC 启动器
echo ================================================
echo.

rem --- 步骤1: 检查 Python ---
set PYTHON_CMD=
if exist "venv\Scripts\python.exe" set PYTHON_CMD=venv\Scripts\python.exe
if "!PYTHON_CMD!"=="" (
    where python >nul 2>&1
    if !errorlevel! equ 0 set PYTHON_CMD=python
)

if "!PYTHON_CMD!"=="" (
    echo [错误] 未找到 Python!
    echo.
    echo 请先安装 Python 3.10+ https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

echo [1/4] 检查 Python 环境...
echo       路径: !PYTHON_CMD!
!PYTHON_CMD! --version 2>&1
echo.

rem --- 步骤2: 检查/创建 venv ---
echo [2/4] 检查虚拟环境...
if not exist "venv\Scripts\python.exe" (
    echo       首次运行，正在创建虚拟环境...
    !PYTHON_CMD! -m venv venv
    if !errorlevel! neq 0 (
        echo [错误] 创建虚拟环境失败!
        pause
        exit /b 1
    )
    echo       [OK] 虚拟环境已创建
) else (
    echo       [OK] 虚拟环境已就绪
)
echo.

rem --- 步骤3: 检查依赖 ---
echo [3/4] 检查依赖包...
set VENV_PYTHON=venv\Scripts\python.exe
!VENV_PYTHON! -c "import PyQt6, dxcam, keyboard, rapidocr_onnxruntime, PIL, numpy" >nul 2>&1
if !errorlevel! neq 0 (
    echo       依赖缺失，正在安装（首次运行约需 1-3 分钟）...
    echo       使用腾讯云镜像加速下载
    echo       --------------------------------------------
    if exist "requirements.txt" (
        !VENV_PYTHON! -m pip install -r requirements.txt -i https://mirrors.cloud.tencent.com/pypi/simple
    ) else (
        echo [警告] 未找到 requirements.txt
    )
    if !errorlevel! neq 0 (
        echo [错误] 依赖安装失败! 请检查网络后重试。
        pause
        exit /b 1
    )
    echo       [OK] 依赖安装完成
) else (
    echo       [OK] 所有依赖已就绪
)
echo.

rem --- 步骤4: 启动程序 ---
echo [4/4] 正在启动 WARFRAME-RELIC...
echo.
!VENV_PYTHON! main.py

rem --- 退出处理 ---
if !errorlevel! neq 0 (
    echo.
    echo ==============================================
    echo   程序异常退出 (错误码: !errorlevel!)
    echo ==============================================
    echo.
    pause
)

endlocal
