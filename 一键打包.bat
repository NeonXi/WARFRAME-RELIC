@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
title WARFRAME-RELIC 一键打包

set START_TIME=%time%

echo.
echo ============================================================
echo         WARFRAME-RELIC - 一键打包 v3.4
echo ============================================================
echo.
echo  本脚本将自动完成:
echo    1. 检查 Python 虚拟环境
echo    2. PyInstaller 打包 (带进度条)
echo    3. 压缩输出文件夹为 .zip
echo    4. 显示最终产物信息
echo.
echo ============================================================
echo.

rem ==========================================
rem Step 1: 检查虚拟环境
rem ==========================================
echo [1/3] 检查 Python 虚拟环境...

if not exist "venv\Scripts\python.exe" (
    echo        [错误] 未找到虚拟环境!
    echo       请先运行 SETUP.bat 初始化开发环境。
    pause
    exit /b 1
)
echo        [OK] 虚拟环境已就绪
echo.

rem ==========================================
rem Step 2: PyInstaller 打包
rem ==========================================
echo [2/3] PyInstaller 打包...
echo        (首次约 3-8 分钟, 后续 1-3 分钟)
echo.
echo ============================================================
echo.

venv\Scripts\python.exe build_exe.py

if !errorlevel! neq 0 (
    echo.
    echo ============================================================
    echo   [失败] 打包过程出错! 请查看上方错误信息。
    echo ============================================================
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo       打包成功!
echo ============================================================
echo.

rem ==========================================
rem Step 3: 压缩为 zip
rem ==========================================
echo [3/3] 正在压缩为 .zip ...

set OUTPUT_DIR=dist\WARFRAME-RELIC
set ZIP_NAME=WARFRAME-RELIC_v3.4.0.zip

if not exist "%OUTPUT_DIR%" (
    echo        [错误] 输出目录不存在: %OUTPUT_DIR%
    pause
    exit /b 1
)

rem 删除旧 zip
if exist "%ZIP_NAME%" (
    echo        删除旧压缩包...
    del /f /q "%ZIP_NAME%"
)

echo        正在压缩 (使用 PowerShell Compress-Archive)...
powershell -NoProfile -Command ^
    "$src = '%OUTPUT_DIR%'; $dst = '%ZIP_NAME%';" ^
    "if (Test-Path $dst) { Remove-Item $dst -Force };" ^
    "Compress-Archive -Path $src -DestinationPath $dst -CompressionLevel Optimal;" ^
    "if ($?) { $size = [math]::Round((Get-Item $dst).Length / 1MB, 1); Write-Host \"        [OK] 压缩完成: $dst ($size MB)\" } else { Write-Host \"        [失败] 压缩出错!\" ; exit 1 }"

if !errorlevel! neq 0 (
    echo        [警告] 压缩失败, 但打包产物在 dist\WARFRAME-RELIC\ 中
    pause
    exit /b 1
)

echo.

rem ==========================================
rem 完成
rem ==========================================
set END_TIME=%time%

echo ============================================================
echo         打包完成!
echo ============================================================
echo.
echo   产物:
echo     [1] dist\WARFRAME-RELIC\     (可运行文件夹)
echo     [2] %ZIP_NAME%                (压缩包, 可直接上传 Release)
echo.

rem 计算文件大小
if exist "%ZIP_NAME%" (
    for %%A in ("%ZIP_NAME%") do echo   压缩包大小: %%~zA bytes
)
echo.

rem 列出 dist 目录主要文件
if exist "%OUTPUT_DIR%\WARFRAME-RELIC.exe" (
    for %%A in ("%OUTPUT_DIR%\WARFRAME-RELIC.exe") do echo   EXE 大小: %%~zA bytes
)

echo.
echo   开始时间: %START_TIME%
echo   结束时间: %END_TIME%
echo.
echo   下一步:
echo     访问 https://github.com/NeonXi/WARFRAME-RELIC/releases/new
echo     上传 %ZIP_NAME% 并填写版本信息
echo.
echo ============================================================
echo.

pause
endlocal
