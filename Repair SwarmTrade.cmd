@echo off
setlocal
cd /d "%~dp0"
title SwarmTrade Repair

echo This will delete only generated local dependencies/build files:
echo   .venv

echo   frontend\node_modules

echo   frontend\dist

echo Your source code and Darwin data are preserved.
echo.
pause
if exist ".venv" rmdir /s /q ".venv"
if exist "frontend\node_modules" rmdir /s /q "frontend\node_modules"
if exist "frontend\dist" rmdir /s /q "frontend\dist"
echo.
echo Repair cleanup done. Starting SwarmTrade...
call "Start SwarmTrade.cmd"
