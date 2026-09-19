$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$logRoot = Join-Path $projectRoot 'data'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$launcherLog = Join-Path $logRoot 'launcher.log'

function Log([string]$Message) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Write-Host $line
    Add-Content -LiteralPath $launcherLog -Value $line
}
function Fail([string]$Message) {
    Log "ERROR: $Message"
    throw $Message
}
function Cmd-Exists([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

Set-Content -LiteralPath $launcherLog -Value "SwarmTrade launcher started $(Get-Date -Format o)"
Log "Project root: $projectRoot"

# ---- Python detection -------------------------------------------------------
$pythonLauncher = $null
$pythonArgs = @()
if (Cmd-Exists 'py.exe') {
    foreach ($selector in @('-3.13','-3.12','-3.11','-3')) {
        try {
            $v = & py.exe $selector -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $v) {
                $parts = $v.Trim().Split('.')
                if ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 11) {
                    $pythonLauncher = 'py.exe'; $pythonArgs = @($selector); break
                }
            }
        } catch {}
    }
}
if (-not $pythonLauncher -and (Cmd-Exists 'python.exe')) {
    try {
        $v = & python.exe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        $parts = $v.Trim().Split('.')
        if ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 11) { $pythonLauncher = 'python.exe' }
    } catch {}
}
if (-not $pythonLauncher) {
    Fail 'Python 3.11+ was not found. Install Python 3.12 from python.org, enable "Add Python to PATH", then run this launcher again.'
}
Log "Python launcher: $pythonLauncher $($pythonArgs -join ' ')"

$venvRoot = Join-Path $projectRoot '.venv'
$pythonExe = Join-Path $venvRoot 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    Log 'Creating Python virtual environment...'
    & $pythonLauncher @pythonArgs -m venv $venvRoot
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonExe)) { Fail 'Could not create .venv.' }
}

# Install/repair runtime dependencies. This is intentionally lightweight: pyarrow is optional.
$runtimeReq = Join-Path $projectRoot 'backend\requirements-runtime.txt'
Log 'Checking Python runtime dependencies...'
$check = & $pythonExe -c "import fastapi,uvicorn,httpx,websockets,numpy,dotenv,hyperliquid; print('ok')" 2>$null
if ($LASTEXITCODE -ne 0 -or $check.Trim() -ne 'ok') {
    Log 'Installing/repairing Python dependencies...'
    & $pythonExe -m pip install --disable-pip-version-check --upgrade pip
    if ($LASTEXITCODE -ne 0) { Fail 'pip upgrade failed.' }
    & $pythonExe -m pip install --disable-pip-version-check -r $runtimeReq
    if ($LASTEXITCODE -ne 0) { Fail 'Backend dependency installation failed. Check internet access and launcher.log.' }
}
Log 'Python backend dependencies: OK'

# ---- Frontend one-time build ------------------------------------------------
$frontendRoot = Join-Path $projectRoot 'frontend'
$distIndex = Join-Path $frontendRoot 'dist\index.html'
if (-not (Test-Path -LiteralPath $distIndex)) {
    if (-not (Cmd-Exists 'node.exe')) { Fail 'Node.js was not found. Install Node.js 22 LTS, then rerun Start SwarmTrade.cmd.' }
    if (-not (Cmd-Exists 'npm.cmd')) { Fail 'npm was not found. Reinstall Node.js 22 LTS with npm.' }
    $nodeVersionRaw = (& node.exe --version).TrimStart('v')
    Log "Node.js: $nodeVersionRaw"
    Push-Location $frontendRoot
    try {
        Log 'Installing frontend dependencies (first launch only)...'
        & npm.cmd ci --no-audit --no-fund --prefer-offline
        if ($LASTEXITCODE -ne 0) { Fail 'npm ci failed. See launcher.log.' }
        Log 'Building frontend (first launch only)...'
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $distIndex)) { Fail 'Frontend build failed. See launcher.log.' }
    } finally { Pop-Location }
}
Log 'Frontend build: OK'

# ---- Backend single-process runtime ----------------------------------------
$backendUrl = 'http://127.0.0.1:8000'
$expectedVersion = '0.11.0'
$backendReady = $false
$probe = $null
try {
    $probe = Invoke-RestMethod "$backendUrl/api/health" -TimeoutSec 2
    $backendReady = $probe.version -eq $expectedVersion
    if (-not $backendReady) {
        Fail "Port 8000 already answers, but version '$($probe.version)' is not expected '$expectedVersion'. Run Stop SwarmTrade.cmd, then start again."
    }
} catch {
    if ($_.Exception.Message -like 'Port 8000 already answers*') { throw }
}

if (-not $backendReady) {
    try {
        $listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction Stop | Select-Object -First 1
        if ($listener) { Fail "Port 8000 is already occupied by PID $($listener.OwningProcess). Close that process or run Stop SwarmTrade.cmd." }
    } catch {
        if ($_.Exception.Message -like 'Port 8000 is already occupied*') { throw }
    }
    Log 'Starting SwarmTrade backend on port 8000...'
    $outLog = Join-Path $logRoot 'backend.log'
    $errLog = Join-Path $logRoot 'backend-error.log'
    if (Test-Path $errLog) { Remove-Item $errLog -Force }
    Start-Process -FilePath $pythonExe -ArgumentList '-m','uvicorn','main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog | Out-Null
}

for ($attempt = 1; $attempt -le 45; $attempt++) {
    try {
        $api = Invoke-RestMethod "$backendUrl/api/health" -TimeoutSec 2
        $page = Invoke-WebRequest "$backendUrl/" -TimeoutSec 2 -UseBasicParsing
        if ($api.version -eq $expectedVersion -and $page.StatusCode -eq 200) {
            Log "READY: $backendUrl"
            Start-Process $backendUrl
            exit 0
        }
    } catch {}
    Start-Sleep -Seconds 1
}

$tail = ''
$errFile = Join-Path $logRoot 'backend-error.log'
if (Test-Path $errFile) {
    $tail = (Get-Content $errFile -Tail 30 -ErrorAction SilentlyContinue) -join "`n"
    Add-Content -LiteralPath $launcherLog -Value "--- backend-error.log tail ---`n$tail"
}
Fail "SwarmTrade did not become ready on port 8000. Check data\backend-error.log. $tail"
