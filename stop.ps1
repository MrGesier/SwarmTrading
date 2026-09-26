$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$record = Join-Path $projectRoot 'data\runtime-pid.txt'
if (-not (Test-Path -LiteralPath $record)) { Write-Host 'No managed runtime recorded.'; exit 0 }
$runtimeId = [int](Get-Content -LiteralPath $record -Raw)
$running = Get-Process -Id $runtimeId -ErrorAction SilentlyContinue
if ($running) {
    New-Item -ItemType File -Path (Join-Path $projectRoot "data\stop-$runtimeId") -Force | Out-Null
    if (-not $running.WaitForExit(20000)) { throw "PID $runtimeId did not stop gracefully; inspect backend-error.log. No forced termination was performed." }
}
Write-Host 'SwarmTrade stopped.'
