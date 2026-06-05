@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title WARFRAME-RELIC - Setup

echo.
echo ============================================================
echo       WARFRAME-RELIC - Environment Setup
echo ============================================================
echo.

:: ============================================================
:: 1. Detect Python
:: ============================================================
echo [1/4] Detecting Python...

set "PYTHON_CMD="

:: 1a. Use existing venv if present
if exist "venv\Scripts\python.exe" (
    set "PYTHON_CMD=venv\Scripts\python.exe"
    echo   [OK] Found existing venv
    goto :skip_venv
)

:: 1b. Search system Python
where python >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=2" %%v in ('python --version 2^>nul') do set "PY_VER=%%v"
    if defined PY_VER (
        set "PYTHON_CMD=python"
        echo   [OK] Found Python !PY_VER! (system PATH)
    )
)

if not defined PYTHON_CMD (
    where python3 >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=2" %%v in ('python3 --version 2^>nul') do set "PY_VER=%%v"
        if defined PY_VER (
            set "PYTHON_CMD=python3"
            echo   [OK] Found Python !PY_VER! (python3)
        )
    )
)

if not defined PYTHON_CMD (
    echo.
    echo   [ERROR] Python not found!
    echo.
    echo   Please install Python 3.12:
    echo     1. Open https://www.python.org/downloads/
    echo     2. Download Python 3.12.x Windows installer (64-bit)
    echo     3. Check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

echo.

:: ============================================================
:: 2. Create virtual environment
:: ============================================================
echo [2/4] Creating virtual environment...

%PYTHON_CMD% -m venv venv
if %errorlevel% neq 0 (
    echo   [WARN] venv failed, trying virtualenv...
    %PYTHON_CMD% -m pip install virtualenv -q 2>&1
    %PYTHON_CMD% -m virtualenv venv 2>&1
    if !errorlevel! neq 0 (
        echo   [WARN] virtualenv also failed, using system Python directly
        set "PYTHON_CMD=python"
        goto :skip_venv
    )
)

echo   [OK] Virtual environment created

set "PYTHON_CMD=venv\Scripts\python.exe"

:skip_venv
echo.

:: ============================================================
:: 3. Install dependencies
:: ============================================================
echo [3/4] Installing dependencies...

:: Upgrade pip first
echo   [+] Upgrading pip...
%PYTHON_CMD% -m pip install --upgrade pip -q 2>&1

:: Try multiple mirrors
echo   [+] Installing packages from requirements.txt...
echo.

set "MIRRORS=https://pypi.org/simple https://mirrors.cloud.tencent.com/pypi/simple https://pypi.tuna.tsinghua.edu.cn/simple https://mirrors.aliyun.com/pypi/simple"
set "INSTALL_OK=0"
set "COUNT=0"

for %%m in (%MIRRORS%) do (
    set /a COUNT+=1
    echo   [Attempt !COUNT!/4] %%m
    %PYTHON_CMD% -m pip install -r requirements.txt -i %%m --timeout=120 2>&1
    if !errorlevel! equ 0 (
        set "INSTALL_OK=1"
        echo   [OK] Dependencies installed
        goto :install_done
    )
    echo   [WARN] This mirror failed, trying next...
    echo.
)

:install_done
if %INSTALL_OK% equ 0 (
    echo.
    echo   [ERROR] All mirrors failed!
    echo.
    echo   Possible reasons:
    echo     1. No internet connection
    echo     2. Firewall / antivirus blocking
    echo     3. Proxy required
    echo.
    echo   Try manually:
    echo     pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo.

:: ============================================================
:: 4. Verify installation
:: ============================================================
echo [4/4] Verifying installation...

set "ALL_OK=1"
for %%m in (PyQt6 dxcam keyboard rapidocr_onnxruntime cv2 PIL numpy pypinyin) do (
    %PYTHON_CMD% -c "import %%m" >nul 2>&1
    if !errorlevel! equ 0 (
        echo   [OK] %%m
    ) else (
        echo   [FAIL] %%m
        set "ALL_OK=0"
    )
)

echo.

if %ALL_OK% equ 0 (
    echo   [WARN] Some modules are missing, please check manually.
) else (
    echo   [OK] All modules verified!
)

:: Clean up
del /q python-installer.exe >nul 2>&1

echo.
echo ============================================================
echo       Setup Complete!
echo ============================================================
echo.
echo   How to run:
echo     - Dev mode : DEV_RUN.bat
echo     - Direct   : venv\Scripts\python.exe main.py
echo.

pause
endlocal
