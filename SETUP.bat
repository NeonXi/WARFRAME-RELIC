@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title WARFRAME-RELIC Setup

:: Force ASCII mode to avoid UTF-8 encoding issues with cmd.exe
chcp 437 >nul 2>&1

echo.
echo ============================================================
echo       WARFRAME-RELIC - Environment Setup
echo ============================================================
echo.

rem ==========================================
rem 0. Check Python
rem ==========================================
echo [0/5] Checking Python...

set PYTHON_CMD=
set PYTHON_VER=

:: Try py launcher first
where py >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=2" %%v in ('py -3 --version 2^>nul') do set PYTHON_VER=%%v
    if defined PYTHON_VER (
        set "PYTHON_CMD=py -3"
        echo   [OK] Python !PYTHON_VER! found (py launcher)
    )
)

:: Try python
if not defined PYTHON_CMD (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=2" %%v in ('python --version 2^>nul') do set PYTHON_VER=%%v
        set "PYTHON_CMD=python"
        echo   [OK] Python !PYTHON_VER! found (PATH)
    )
)

:: Try python3
if not defined PYTHON_CMD (
    where python3 >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=2" %%v in ('python3 --version 2^>nul') do set PYTHON_VER=%%v
        set "PYTHON_CMD=python3"
        echo   [OK] Python !PYTHON_VER! found (PATH)
    )
)

:: Auto download and install Python if not found
if not defined PYTHON_CMD (
    echo   [INFO] Python not found, will download and install automatically...
    echo.
    
    set "PYTHON_URL=https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe"
    set "PYTHON_INSTALLER=python-installer.exe"
    
    echo   Downloading Python 3.12.4...
    powershell -Command "(New-Object Net.WebClient).DownloadFile('%PYTHON_URL%', '%PYTHON_INSTALLER%')"
    if !errorlevel! neq 0 (
        echo   [ERROR] Failed to download Python!
        echo   Please download manually from: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    
    echo   Installing Python...
    echo   This may take a few minutes...
    %PYTHON_INSTALLER% /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    if !errorlevel! neq 0 (
        echo   [ERROR] Python installation failed!
        pause
        exit /b 1
    )
    
    del %PYTHON_INSTALLER% >nul 2>&1
    echo   [OK] Python installed successfully
    
    :: Refresh PATH and find Python
    set "PYTHON_CMD=python"
    set PYTHON_VER=3.12.4
)

echo.

rem ==========================================
rem 1. Create virtual environment
rem ==========================================
echo [1/5] Creating virtual environment (venv)...

if exist "venv\Scripts\python.exe" (
    echo   [SKIP] venv already exists
) else (
    echo   Creating venv...
    %PYTHON_CMD% -m venv venv 2>&1
    if !errorlevel! neq 0 (
        echo.
        echo   [ERROR] Failed to create venv!
        echo.
        echo   Possible reasons:
        echo   1. Insufficient permissions (try running as Administrator)
        echo   2. Python venv module not installed
        echo   3. Disk space issue
        echo   4. Antivirus blocking the operation
        echo.
        echo   Trying alternative method with virtualenv...
        %PYTHON_CMD% -m pip install virtualenv -q
        if !errorlevel! equ 0 (
            %PYTHON_CMD% -m virtualenv venv 2>&1
            if !errorlevel! equ 0 (
                echo   [OK] venv created with virtualenv
                goto :venv_created
            )
        )
        echo.
        echo   [ERROR] All methods failed!
        echo   Please try:
        echo   1. Run this script as Administrator
        echo   2. Manually create venv: python -m venv venv
        echo   3. Check disk space and permissions
        pause
        exit /b 1
    )
    echo   [OK] venv created
)
:venv_created

echo.

rem ==========================================
rem 2. Upgrade pip
rem ==========================================
echo [2/5] Upgrading pip...

venv\Scripts\python.exe -m pip install --upgrade pip -i https://mirrors.cloud.tencent.com/pypi/simple --quiet
if %errorlevel% neq 0 (
    echo   [WARN] pip upgrade failed, continuing...
) else (
    echo   [OK] pip is up to date
)

echo.

rem ==========================================
rem 3. Install dependencies
rem ==========================================
echo [3/5] Installing dependencies...
echo   (Trying Tencent Cloud mirror first, fallback to PyPI)
echo.

venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.cloud.tencent.com/pypi/simple
if %errorlevel% neq 0 (
    echo.
    echo   [WARN] Mirror failed, trying PyPI official...
    echo.
    venv\Scripts\python.exe -m pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo.
        echo   [ERROR] Dependency installation failed!
        echo   Please check your network and try again.
        echo.
        pause
        exit /b 1
    )
)

echo.
echo   [OK] Dependencies installed

echo.

rem ==========================================
rem 4. Verify environment
rem ==========================================
echo [4/5] Verifying environment...

echo.
echo   Checking modules...

set ALL_OK=1

for %%m in (PyQt6 dxcam keyboard rapidocr_onnxruntime cv2 PIL numpy pypinyin) do (
    venv\Scripts\python.exe -c "import %%m" >nul 2>&1
    if !errorlevel! equ 0 (
        echo     [+] %%m
    ) else (
        echo     [-] %%m - MISSING!
        set ALL_OK=0
    )
)

echo.

if %ALL_OK% equ 0 (
    echo   [WARN] Some modules are missing, manual install may be needed
) else (
    echo   [OK] All modules verified!
)

echo.

rem ==========================================
rem 5. Cleanup
rem ==========================================
echo [5/5] Final cleanup...

:: Remove temporary files
del /q python-installer.exe >nul 2>&1
echo   [OK] Cleanup done

echo.

rem ==========================================
rem Done
rem ==========================================
echo ============================================================
echo       Setup Complete!
echo ============================================================
echo.
echo   How to start:
echo     1. Dev mode (recommended): Run DEV_RUN.bat
echo     2. Direct launch:          Run WARFRAME-RELIC.bat
echo     3. Command line:           venv\Scripts\python.exe main.py
echo.
echo   Build executable:
echo     Run pack.bat
echo.
echo ============================================================

pause
endlocal