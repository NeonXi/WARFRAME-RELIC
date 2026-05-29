@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
title WARFRAME-RELIC 环境初始化

echo.
echo ============================================================
echo     WARFRAME-RELIC - 首次运行环境配置
echo ============================================================
echo.
echo  本脚本将自动完成:
echo    1. 检测/安装 Python 3.10+
echo    2. 创建虚拟环境
echo    3. 安装项目依赖
echo    4. 启动程序
echo.
echo ============================================================
echo.

rem ==========================================
rem 步骤 1: 检查是否已有 Python
rem ==========================================
set PYTHON_INSTALLER=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
set PYTHON_EXE=

echo [1/4] 检测 Python 环境...

:: 1a. 先检查项目内的便携 Python
if exist "python\python.exe" (
    set PYTHON_EXE=python\python.exe
    echo       [OK] 发现便携 Python: python\python.exe
    goto :create_venv
)

:: 1b. 检查系统 PATH 中的 Python
where python >nul 2>&1
if !errorlevel! equ 0 (
    for /f "delims=" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
    echo       [OK] 发现系统 Python: !PY_VER!
    :: 检查版本是否 >= 3.10
    python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if !errorlevel! equ 0 (
        set PYTHON_EXE=python
        goto :create_venv
    ) else (
        echo       [警告] Python 版本过低，需要 3.10+
    )
)

:: 1c. 检查常见安装路径
for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%PROGRAMFILES%\Python311\python.exe"
    "%PROGRAMFILES%\Python312\python.exe"
    "%PROGRAMFILES%\Python313\python.exe"
    "C:\Python311\python.exe"
    "C:\Python312\python.exe"
) do (
    if exist %%p (
        set PYTHON_EXE=%%p
        echo       [OK] 发现 Python: %%p
        goto :create_venv
    )
)

:: 1d. 都没找到，询问用户是否自动安装
echo.
echo       [未找到] 系统中未检测到 Python 3.10+
echo.
echo       Python 是运行本程序所必需的。
echo       是否自动下载并安装 Python 3.11.9？
echo       (约 25 MB，安装过程约 1-2 分钟)
echo.
choice /c YN /n /m "       [Y] 自动安装  [N] 手动安装后重试: "
if errorlevel 2 goto :manual_install
if errorlevel 1 goto :auto_install

:auto_install
echo.
echo [*] 正在下载 Python 3.11.9...
echo     下载地址: %PYTHON_INSTALLER%
echo.

set PYTHON_INSTALLER_PATH=%TEMP%\python-3.11.9-amd64.exe

:: 使用 PowerShell 下载（Win10+ 自带）
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_INSTALLER%' -OutFile '%PYTHON_INSTALLER_PATH%'" 2>&1
if !errorlevel! neq 0 (
    echo.
    echo [错误] 下载失败！请检查网络连接。
    echo 你也可以手动下载安装 Python 3.10+:
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo       [OK] 下载完成
echo.
echo [*] 正在安装 Python 3.11.9...
echo     (请在弹出的安装窗口中点击 Install 完成安装)
echo.

:: 静默安装 + 添加到 PATH
"%PYTHON_INSTALLER_PATH%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
if !errorlevel! neq 0 (
    echo [警告] 自动安装可能失败，尝试弹窗安装...
    "%PYTHON_INSTALLER_PATH%"
    echo.
    echo 请在安装完成后按任意键继续...
    pause >nul
)

:: 刷新 PATH 环境变量
call :refresh_env

:: 再次检测
where python >nul 2>&1
if !errorlevel! equ 0 (
    set PYTHON_EXE=python
    echo       [OK] Python 安装成功！
    goto :create_venv
)

:: 检查安装路径
for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%PROGRAMFILES%\Python311\python.exe"
) do (
    if exist %%p (
        set PYTHON_EXE=%%p
        echo       [OK] 发现 Python: %%p
        goto :create_venv
    )
)

echo.
echo [错误] Python 安装后仍无法找到。请手动安装：
echo        https://www.python.org/downloads/
echo        (安装时务必勾选 "Add Python to PATH")
echo.
pause
exit /b 1

:manual_install
echo.
echo 请手动安装 Python 3.10+:
echo   下载地址: https://www.python.org/downloads/
echo   安装时务必勾选 "Add Python to PATH"
echo.
echo 安装完成后重新运行本脚本即可。
echo.
pause
exit /b 1

:create_venv
echo.
echo [2/4] 创建虚拟环境...
if not exist "venv\Scripts\python.exe" (
    "!PYTHON_EXE!" -m venv venv
    if !errorlevel! neq 0 (
        echo [错误] 创建虚拟环境失败！
        pause
        exit /b 1
    )
    echo       [OK] 虚拟环境已创建
) else (
    echo       [OK] 虚拟环境已存在
)

:install_deps
echo.
echo [3/4] 安装项目依赖...
echo       (首次安装约需 1-3 分钟，请耐心等待)
echo.

venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.cloud.tencent.com/pypi/simple --quiet
if !errorlevel! neq 0 (
    echo.
    echo [警告] 腾讯云镜像失败，尝试官方源...
    venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
    if !errorlevel! neq 0 (
        echo [错误] 依赖安装失败！请检查网络后重试。
        pause
        exit /b 1
    )
)

echo       [OK] 依赖安装完成

:launch
echo.
echo [4/4] 正在启动 WARFRAME-RELIC...
echo.
echo ============================================================
echo.
start "" venv\Scripts\python.exe main.py

echo 程序已启动！以后直接双击 WARFRAME-RELIC.bat 即可。
echo.
timeout /t 3 >nul
exit /b 0

:refresh_env
:: 通过注册表刷新当前进程的 PATH
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul') do set "SysPath=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set "UserPath=%%b"
set "PATH=%SysPath%;%UserPath%;%PATH%"
goto :eof
