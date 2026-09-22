param([switch]$Check)
$ErrorActionPreference='Stop'
$demoRoot=[IO.Path]::GetFullPath($PSScriptRoot)
$demoPython=Join-Path $demoRoot '.venv\Scripts\python.exe'
$env:HYPERLIQUID_ENABLED='false'
$env:DARWIN_AUTOSTART_MODE='simulation'
if(-not $env:CODEX_HOME){$env:CODEX_HOME=Join-Path $env:USERPROFILE '.codex'}
$codexCommand=Get-Command codex -ErrorAction SilentlyContinue
if($codexCommand){$env:DARWIN_CODEX_BIN=$codexCommand.Source}
elseif(-not $env:DARWIN_CODEX_BIN){
  $desktopCli=Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\bin') -Directory -ErrorAction SilentlyContinue |
    ForEach-Object {Get-Item -LiteralPath (Join-Path $_.FullName 'codex.exe') -ErrorAction SilentlyContinue} |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if($desktopCli){$env:DARWIN_CODEX_BIN=$desktopCli.FullName}
}
if(-not (Get-Command node -ErrorAction SilentlyContinue)){
  $bundledNode=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin'
  if(Test-Path (Join-Path $bundledNode 'node.exe')){$env:PATH=$bundledNode+';'+$env:PATH}
}
$nodeCommand=Get-Command node -ErrorAction SilentlyContinue
if($nodeCommand){$env:DARWIN_NODE_BIN=$nodeCommand.Source}
if($Check){
  if($env:DARWIN_CODEX_BIN){& $env:DARWIN_CODEX_BIN login status}else{Write-Host 'Codex CLI absent. Installer le CLI officiel puis lancer codex login.'}
  $webSession=New-Object Microsoft.PowerShell.Commands.WebRequestSession
  $null=Invoke-RestMethod 'http://127.0.0.1:8000/api/autocorrection/session' -WebSession $webSession
  $health=Invoke-RestMethod 'http://127.0.0.1:8000/api/health'
  if(-not $health.paper_only){throw 'Demo requires paper-only mode.'}
  Invoke-RestMethod 'http://127.0.0.1:8000/api/autocorrection/state' -WebSession $webSession | ConvertTo-Json -Depth 5
  exit 0
}
& (Join-Path $demoRoot 'start.ps1') -NoBrowser
if(-not (Test-Path $demoPython)){throw 'Python environment missing. Run Start SwarmTrade.cmd first.'}
$demoData=Join-Path $demoRoot 'data\autocorrection'
New-Item -ItemType Directory -Force -Path $demoData | Out-Null
# Refresh an idle worker so it picks up this version and the resolved CLI path.
$demoSession=New-Object Microsoft.PowerShell.Commands.WebRequestSession
$null=Invoke-RestMethod 'http://127.0.0.1:8000/api/autocorrection/session' -WebSession $demoSession
$demoState=Invoke-RestMethod 'http://127.0.0.1:8000/api/autocorrection/state' -WebSession $demoSession
$activeDemo=@($demoState.jobs | Where-Object {$_.state -in @('QUEUED','PATCHING','LLM_CONNECTED','PROPOSED','TESTING')})
if($activeDemo.Count){Write-Host 'Une validation est en cours. Le worker existant est conserve.'; exit 0}
$workerScript=Join-Path $demoRoot 'backend\demo_worker.py'
$workerProcesses=Get-CimInstance Win32_Process -Filter "name = 'python.exe'" -ErrorAction SilentlyContinue |
  Where-Object {$_.CommandLine -and $_.CommandLine.Contains($workerScript)}
foreach($workerProcess in $workerProcesses){Stop-Process -Id $workerProcess.ProcessId -ErrorAction SilentlyContinue}
# The separate worker owns a cross-process OS lock.
Start-Process -FilePath $demoPython -ArgumentList @('"'+(Join-Path $demoRoot 'backend\demo_worker.py')+'"') -WorkingDirectory $demoRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $demoData 'worker-output.log') -RedirectStandardError (Join-Path $demoData 'worker-error.log')
Start-Process 'http://127.0.0.1:8000/factory'
Write-Host 'Factory ouverte. Panneau Autocorrection / Code Engineer : Demonstration controlee.'
