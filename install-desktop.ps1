$ErrorActionPreference = 'Stop'
$desktopDir = [Environment]::GetFolderPath('Desktop')
$wsh = New-Object -ComObject WScript.Shell
foreach ($item in @(@{Name='SwarmTrading - Mister Gesier';Script='launch.ps1'}, @{Name='Arreter SwarmTrading';Script='stop.ps1'})) {
    $shortcut = $wsh.CreateShortcut((Join-Path $desktopDir ($item.Name + '.lnk')))
    $shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot $item.Script) + '"'
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.Description = 'Swarm Trade by Mister Gesier - application locale'
    $shortcut.WindowStyle = 7
    $icon = Join-Path $PSScriptRoot 'frontend\public\darwin-owl.ico'
    if (Test-Path -LiteralPath $icon) { $shortcut.IconLocation = $icon }
    $shortcut.Save()
    Write-Host ('Created: ' + (Join-Path $desktopDir ($item.Name + '.lnk')))
}
