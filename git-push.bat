@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
title Git Push - WARFRAME-RELIC

echo.
echo ============================================================
echo           WARFRAME-RELIC - Git 一键推送
echo ============================================================
echo.

rem --- 检查是否在 git 仓库中 ---
git rev-parse --is-inside-work-tree >nul 2>&1
if !errorlevel! neq 0 (
    echo [错误] 当前目录不是 Git 仓库！
    pause
    exit /b 1
)

rem --- 显示当前分支 ---
for /f "delims=" %%i in ('git rev-parse --abbrev-ref HEAD') do set BRANCH=%%i
echo [当前分支] !BRANCH!
echo.

rem --- 显示变更状态 ---
echo [变更状态]
git status --short
echo.

rem --- 确认是否继续 ---
set /p CONFIRM="是否提交并推送这些变更？(Y/N): "
if /i not "!CONFIRM!"=="Y" (
    echo 已取消。
    pause
    exit /b 0
)
echo.

rem --- 提交信息 ---
set /p COMMIT_MSG="请输入提交信息（留空使用默认）: "
if "!COMMIT_MSG!"=="" (
    set COMMIT_MSG=update
)
echo.

rem --- 执行 git 操作 ---
echo [1/3] git add -A ...
git add -A
if !errorlevel! neq 0 (
    echo [错误] git add 失败！
    pause
    exit /b 1
)

echo [2/3] git commit ...
git commit -m "!COMMIT_MSG!"
if !errorlevel! neq 0 (
    echo [提示] 没有需要提交的变更，或提交失败。
)

echo [3/3] git push ...
git push origin !BRANCH!
if !errorlevel! neq 0 (
    echo [错误] 推送失败！请检查网络或远程仓库设置。
    pause
    exit /b 1
)

echo.
echo ============================================================
echo           推送成功！
echo ============================================================
echo.
pause
endlocal
