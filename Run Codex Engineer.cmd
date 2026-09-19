@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist data mkdir data

echo.
echo ============================================================
echo   SWARMTRADE V0.11 - CODEX ENGINEER (CODE ONLY / NO CAPITAL)
echo ============================================================
echo.

where codex >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Codex CLI was not found in PATH.
  echo Install/login to Codex first, then run this file again.
  echo See CODEX_ENGINEER.md.
  pause
  exit /b 1
)

set "TASKFILE=data\codex-engineer-task.json"
set "PROMPTFILE=data\codex-engineer-prompt.txt"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$body = @{symbol='BTCUSDT';mode='simulation';objective='Inspect SwarmTrade Darwin V0.11, fix the highest-value reliability/research issue you can verify, preserve all capital-safety invariants, add tests, and report exact validation evidence.'} ^| ConvertTo-Json; try { $r = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/engineer/task' -ContentType 'application/json' -Body $body -TimeoutSec 4; $r ^| ConvertTo-Json -Depth 20 ^| Set-Content -Encoding UTF8 '%TASKFILE%'; exit 0 } catch { exit 2 }"
if errorlevel 2 (
  echo [INFO] Local SwarmTrade API not reachable; Codex will work from repository evidence only.
) else (
  echo [OK] Research task pack exported to %TASKFILE%
)

> "%PROMPTFILE%" echo You are CODEX ENGINEER for SwarmTrade Darwin V0.11.
>> "%PROMPTFILE%" echo Read AGENTS.md first and obey every safety invariant.
>> "%PROMPTFILE%" echo Then read CODEX_HANDOFF.md, OPENAI_BRAIN_ARCHITECTURE.md and FACTORY_ARCHITECTURE.md.
>> "%PROMPTFILE%" echo If data/codex-engineer-task.json exists, use it as read-only research evidence.
>> "%PROMPTFILE%" echo Inspect the repository. Fix the highest-value reliability or research-quality issue you can actually verify.
>> "%PROMPTFILE%" echo Prefer launcher/build reliability first if the application cannot start on Windows.
>> "%PROMPTFILE%" echo Make bounded changes, add/update tests, run backend tests and frontend build if dependencies are available.
>> "%PROMPTFILE%" echo Do not enable live trading, do not weaken CERBERUS/JUDGE authority, do not touch secrets, do not commit/push/deploy automatically.
>> "%PROMPTFILE%" echo Finish with a concise report of changed files, tests, failures, and remaining risks.

echo [INFO] Starting Codex with workspace-write sandbox...
type "%PROMPTFILE%" | codex exec --sandbox workspace-write -
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo [OK] Codex task completed. Review the diff before keeping it.
) else (
  echo [ERROR] Codex exited with code %RC%.
)
pause
exit /b %RC%
