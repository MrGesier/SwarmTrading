$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
try {
    $api = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 2
    if ($api.project_root -eq $projectRoot) { Invoke-RestMethod -Method Post 'http://127.0.0.1:8000/api/flush' -TimeoutSec 15 | Out-Null }
} catch { Write-Host 'Backend unavailable; checking local processes.' }
$rootPattern = [regex]::Escape($projectRoot + '\backend')
$owned = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match $rootPattern -and $_.CommandLine -match 'uvicorn|serve_ui\.py' }
foreach ($process in $owned) { Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue }
Write-Host 'SwarmTrading stopped.'
