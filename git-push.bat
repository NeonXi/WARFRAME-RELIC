@echo off
setlocal enabledelayedexpansion
chcp 437 >nul 2>&1
cd /d "%~dp0"
title Git Push - WARFRAME-RELIC

echo.
echo ============================================================
echo         WARFRAME-RELIC - Git Push
echo ============================================================
echo.

rem --- Check if inside a git repo ---
git rev-parse --is-inside-work-tree >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] Not a Git repository!
    pause
    exit /b 1
)

rem --- Show current branch ---
for /f "delims=" %%i in ('git rev-parse --abbrev-ref HEAD') do set BRANCH=%%i
echo [Branch] !BRANCH!
echo.

rem --- Pull latest changes first ---
echo [0/4] Pulling latest changes...
git pull --rebase origin !BRANCH!
if !errorlevel! neq 0 (
    echo [WARN] Pull failed or no remote updates. Continuing...
)
echo.

rem --- Show changes ---
echo [Changes]
git status --short
echo.

rem --- Confirm ---
set /p CONFIRM="Commit and push these changes? (Y/N): "
if /i not "!CONFIRM!"=="Y" (
    echo Cancelled.
    pause
    exit /b 0
)
echo.

rem --- Commit message ---
set /p COMMIT_MSG="Enter commit message (leave blank for default): "
if "!COMMIT_MSG!"=="" (
    set COMMIT_MSG=update
)
echo.

rem --- Execute git operations ---
echo [1/4] git add -A ...
git add -A
if !errorlevel! neq 0 (
    echo [ERROR] git add failed!
    pause
    exit /b 1
)

echo [2/4] git commit ...
git commit -m "!COMMIT_MSG!"
if !errorlevel! neq 0 (
    echo [INFO] Nothing to commit, or commit failed.
)

echo [3/4] git push ...
git push origin !BRANCH!
if !errorlevel! neq 0 (
    echo [ERROR] Push failed! Check network or remote settings.
    echo.
    echo Try:
    echo   1. Check your internet connection
    echo   2. Use a VPN or proxy if needed
    echo   3. Run: git push origin !BRANCH!
    pause
    exit /b 1
)

echo.
echo ============================================================
echo        Push Successful!
echo ============================================================
echo.
pause
endlocal