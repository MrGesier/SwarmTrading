param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$logRoot = Join-Path $projectRoot 'data'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $pythonExe)) {
    python -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12+ is required.' }
    & $pythonExe -m pip install -r (Join-Path $projectRoot 'backend\requirements.lock.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Backend installation failed.' }
}
$frontendRoot = Join-Path $projectRoot 'frontend'
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'dist\index.html'))) {
    Push-Location $frontendRoot
    try {
        npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed.' }
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
}
function Read-LocalHealth([string]$url) {
    try { return Invoke-RestMethod $url -TimeoutSec 2 } catch { return $null }
}
$api = Read-LocalHealth 'http://127.0.0.1:8000/api/health'
if ($api -and $api.project_root -ne $projectRoot) { throw 'Port 8000 is used by another installation. Stop that instance first.' }
if (-not $api) {
    $backendDir = Join-Path $projectRoot 'backend'
    Start-Process -FilePath $pythonExe -ArgumentList '-m','uvicorn','main:app','--app-dir',('"' + $backendDir + '"'),'--host','127.0.0.1','--port','8000','--log-level','warning' -WorkingDirectory $backendDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'backend.log') -RedirectStandardError (Join-Path $logRoot 'backend-error.log') | Out-Null
}
$ui = Read-LocalHealth 'http://127.0.0.1:3000/local-health'
if ($ui -and $ui.project_root -ne $projectRoot) { throw 'Port 3000 is used by another installation.' }
if (-not $ui) {
    Start-Process -FilePath $pythonExe -ArgumentList ('"' + (Join-Path $projectRoot 'backend\serve_ui.py') + '"') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'frontend.log') -RedirectStandardError (Join-Path $logRoot 'frontend-error.log') | Out-Null
}
for ($attempt = 0; $attempt -lt 45; $attempt++) {
    $api = Read-LocalHealth 'http://127.0.0.1:8000/api/health'
    $ui = Read-LocalHealth 'http://127.0.0.1:3000/local-health'
    if ($api.project_root -eq $projectRoot -and $ui.project_root -eq $projectRoot) {
        Write-Host 'SwarmTrading is ready: http://localhost:3000'
        if (-not $NoBrowser) { Start-Process 'http://localhost:3000' }
        exit 0
    }
    Start-Sleep -Seconds 1
}
throw 'Startup failed. Inspect data/backend-error.log and data/frontend-error.log.'
