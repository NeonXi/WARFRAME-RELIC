@echo off
cd /d "%~dp0"
title Git Push

echo.
echo ============================================================
echo         WARFRAME-RELIC - Git Push
echo ============================================================
echo.

rem -- check git repo
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Not a Git repository
    pause
    exit /b 1
)

rem -- branch
for /f "delims=" %%i in ('git rev-parse --abbrev-ref HEAD') do set BR=%%i
echo Branch: %BR%

rem -- commits ahead
for /f "delims=" %%i in ('git rev-list --count origin/%BR%..HEAD') do set AH=%%i
if "%AH%"=="" set AH=0
if %AH% gtr 0 (
    echo Ahead of remote: %AH% commit(s)
)
echo.

rem -- status
echo ---------- Changes ----------
git status --short
echo ------------------------------
echo.

rem -- untracked
for /f "delims=" %%i in ('git ls-files --others --exclude-standard') do set UT=1
if "%UT%"=="1" (
    echo Warning: untracked files exist (will NOT be staged)
    git ls-files --others --exclude-standard
    echo.
)

rem -- check if anything to do
git diff --quiet
set D=%errorlevel%
git diff --cached --quiet
set S=%errorlevel%
if %D% equ 0 if %S% equ 0 if %AH% equ 0 (
    echo Nothing to commit or push.
    pause
    exit /b 0
)

rem -- confirm
set /p CF="Commit and push? (Y/N): "
if /i not "%CF%"=="Y" (
    echo Cancelled.
    pause
    exit /b 0
)
echo.

rem -- commit message
set /p MS="Commit message (default: update): "
if "%MS%"=="" set MS=update
echo.

rem -- stage
echo [1/4] Staging changes...
git add -u
if errorlevel 1 (
    echo [ERROR] git add failed
    pause
    exit /b 1
)
echo        OK
echo.

rem -- commit (if needed)
git diff --cached --quiet
if errorlevel 1 (
    echo [2/4] Committing...
    git commit -m "%MS%"
    if errorlevel 1 (
        echo [ERROR] Commit failed
        pause
        exit /b 1
    )
    echo        OK
    echo.
) else (
    echo [2/4] Nothing to commit, pushing existing commits...
    echo.
)

rem -- pull
echo [3/4] Pulling from remote...
git pull --rebase origin %BR%
if errorlevel 1 (
    echo [WARN] Pull failed, continuing anyway...
    echo.
) else (
    echo        OK
    echo.
)

rem -- push
echo [4/4] Pushing...
git push origin %BR%
if errorlevel 1 (
    echo.
    echo [ERROR] Push failed
    echo Manual: git push origin %BR%
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo        Push Successful
echo ============================================================
echo.
pause
exit /b 0
