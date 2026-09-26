@echo off
setlocal
cd /d "%~dp0"
title SwarmTrade Darwin Launcher

echo ============================================================
echo   SwarmTrade Darwin - launcher
echo ============================================================
echo.
echo Project: %CD%
echo Log:     %CD%\data\launcher.log
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo ============================================================
  echo SwarmTrade failed to start. Exit code: %EXITCODE%
  echo Open data\launcher.log and data\backend-error.log for details.
  echo ============================================================
  if exist "%~dp0data\launcher.log" notepad.exe "%~dp0data\launcher.log"
  pause
  exit /b %EXITCODE%
)
exit /b 0
