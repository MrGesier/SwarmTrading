$ErrorActionPreference='Stop'
$desktop=[Environment]::GetFolderPath('Desktop')
$shortcutPath=Join-Path $desktop 'Darwin - Hyperliquid Paper.lnk'
$shell=New-Object -ComObject WScript.Shell
$link=$shell.CreateShortcut($shortcutPath)
$link.TargetPath=Join-Path $PSScriptRoot 'Demarrer-Darwin-Paper.cmd'
$link.WorkingDirectory=$PSScriptRoot
$link.IconLocation=(Join-Path $PSScriptRoot 'frontend\public\darwin.ico')+',0'
$link.Description='Darwin : cours actuels Hyperliquid, trading paper et recherche automatique. Aucun ordre reel.'
$link.WindowStyle=7
$link.Save()
if(-not (Test-Path -LiteralPath $shortcutPath)){throw 'Raccourci non cree.'}
Write-Host $shortcutPath
