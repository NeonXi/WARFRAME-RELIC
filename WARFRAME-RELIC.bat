@echo off
setlocal enabledelayedexpansion

:: Use ASCII mode to avoid encoding issues
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
set PYTHON_CMD=
if exist "venv\Scripts\python.exe" (
    set PYTHON_CMD=venv\Scripts\python.exe
    echo [1/4] Found venv Python: !PYTHON_CMD!
)

if "!PYTHON_CMD!"=="" (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        set PYTHON_CMD=python
        echo [1/4] Found system Python: !PYTHON_CMD!
    )
)

if "!PYTHON_CMD!"=="" (
    echo [ERROR] Python not found!
    echo.
    echo Please install Python 3.10+ from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    echo %date% %time% - ERROR: Python not found >> "%LOG_FILE%"
    pause
    exit /b 1
)

echo [1/4] Checking Python environment...
echo       Path: !PYTHON_CMD!
!PYTHON_CMD! --version 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] Failed to run Python!
    echo %date% %time% - ERROR: Failed to run Python >> "%LOG_FILE%"
    pause
    exit /b 1
)
echo %date% %time% - Python OK: !PYTHON_CMD! >> "%LOG_FILE%"
echo.

rem --- Step 2: Check/create venv ---
echo [2/4] Checking virtual environment...
if not exist "venv\Scripts\python.exe" (
    echo       First run, creating virtual environment...
    echo %date% %time% - Creating venv... >> "%LOG_FILE%"
    !PYTHON_CMD! -m venv venv
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create venv!
        echo %date% %time% - ERROR: Failed to create venv >> "%LOG_FILE%"
        echo.
        echo Trying to use system Python directly...
        set "VENV_PYTHON=!PYTHON_CMD!"
        echo %date% %time% - Using system Python >> "%LOG_FILE%"
    ) else (
        echo       [OK] Virtual environment created
        set "VENV_PYTHON=venv\Scripts\python.exe"
    )
) else (
    echo       [OK] Virtual environment ready
    set "VENV_PYTHON=venv\Scripts\python.exe"
)
echo %date% %time% - Venv: !VENV_PYTHON! >> "%LOG_FILE%"
echo.

rem --- Step 3: Check dependencies ---
echo [3/4] Checking dependencies...
!VENV_PYTHON! -c "import PyQt6, dxcam, keyboard, rapidocr_onnxruntime, PIL, numpy, pypinyin" >nul 2>&1
if !errorlevel! neq 0 (
    echo       Missing dependencies, installing (first run may take 1-3 minutes)...
    echo       Using Tencent Cloud mirror
    echo       --------------------------------------------
    echo %date% %time% - Installing dependencies... >> "%LOG_FILE%"
    
    set "MIRRORS=https://mirrors.cloud.tencent.com/pypi/simple https://pypi.tuna.tsinghua.edu.cn/simple https://mirrors.aliyun.com/pypi/simple https://pypi.org/simple"
    set "INSTALL_OK=0"
    
    for %%m in (!MIRRORS!) do (
        if !INSTALL_OK! equ 0 (
            echo       Trying mirror: %%m
            !VENV_PYTHON! -m pip install -r requirements.txt -i %%m --timeout=120
            if !errorlevel! equ 0 (
                set "INSTALL_OK=1"
                echo       [OK] Dependencies installed
                echo %date% %time% - Dependencies installed via %%m >> "%LOG_FILE%"
            )
        )
    )
    
    if !INSTALL_OK! equ 0 (
        echo [ERROR] Failed to install dependencies!
        echo %date% %time% - ERROR: Dependency installation failed >> "%LOG_FILE%"
        echo.
        echo Please check your network connection and try again.
        pause
        exit /b 1
    )
) else (
    echo       [OK] All dependencies ready
)
echo %date% %time% - Dependencies OK >> "%LOG_FILE%"
echo.

rem --- Step 4: Start program ---
echo [4/4] Starting WARFRAME-RELIC...
echo %date% %time% - Starting main.py >> "%LOG_FILE%"
echo.

!VENV_PYTHON! main.py 2>&1
set "EXIT_CODE=!errorlevel!"
echo %date% %time% - Exit code: !EXIT_CODE! >> "%LOG_FILE%"

rem --- Exit handling ---
if !EXIT_CODE! neq 0 (
    echo.
    echo ==============================================
    echo   Program exited abnormally (Error: !errorlevel!)
    echo ==============================================
    echo   Check launch_log.txt for details
    echo ==============================================
    echo %date% %time% - ERROR: Exit code !errorlevel! >> "%LOG_FILE%"
    pause
)

endlocal