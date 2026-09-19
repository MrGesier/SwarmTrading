@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title SwarmTrade V0.11 Diagnostics

echo ============================================================
echo   SwarmTrade Darwin V0.11 - diagnostics
echo ============================================================
echo Project: %CD%
echo.

echo [Python]
where py 2>nul
py -3 --version 2>nul
where python 2>nul
python --version 2>nul
echo.

echo [Node]
where node 2>nul
node --version 2>nul
where npm 2>nul
npm --version 2>nul
echo.

echo [Generated files]
if exist ".venv\Scripts\python.exe" (echo .venv: OK) else (echo .venv: MISSING)
if exist "frontend\dist\index.html" (echo frontend dist: OK) else (echo frontend dist: MISSING - first start must run npm ci/build)
if exist "frontend\node_modules\.bin\tsc.cmd" (echo frontend deps: OK) else (echo frontend deps: MISSING/PARTIAL)
echo.

echo [Port 8000]
netstat -ano | findstr ":8000"
echo.

echo [HTTP health]
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 2; $r ^| ConvertTo-Json -Depth 5 } catch { Write-Host ('NOT READY: ' + $_.Exception.Message) }"
echo.

echo [Brain boundary]
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-RestMethod 'http://127.0.0.1:8000/api/brains/state?symbol=BTCUSDT^&mode=simulation' -TimeoutSec 3; Write-Host ('ATLAS: ' + $r.brains.atlas.runtime + ' / ' + $r.brains.atlas.model); Write-Host ('CURIE: ' + $r.brains.curie.runtime + ' / ' + $r.brains.curie.model); Write-Host ('FORGE: ' + $r.brains.forge.runtime); Write-Host ('CERBERUS: ' + $r.brains.cerberus.runtime); Write-Host ('HERMES: ' + $r.brains.hermes.runtime) } catch { Write-Host 'Unavailable while backend is stopped.' }"
echo.

echo [Last launcher log]
if exist "data\launcher.log" type "data\launcher.log"
echo.
echo [Last backend error]
if exist "data\backend-error.log" type "data\backend-error.log"
echo.
pause
