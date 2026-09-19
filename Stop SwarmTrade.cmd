@echo off
setlocal
echo Stopping SwarmTrade on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr LISTENING ^| findstr ":8000"') do taskkill /PID %%a /F >nul 2>&1
echo Done.
timeout /t 2 >nul
