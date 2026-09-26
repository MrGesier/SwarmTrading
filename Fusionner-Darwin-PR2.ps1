param([switch]$VerifierSeulement)
$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath($PSScriptRoot)
$python=Join-Path $repo '.venv\Scripts\python.exe'
$helperRoot=Join-Path $env:USERPROFILE '.codex\plugins\cache\openai-curated-remote\pr-completion\0.3.0\skills\take-pr-to-completion\scripts'
$land=Join-Path $helperRoot 'pr_land.py'
$watch=Join-Path $helperRoot 'pr_watch.py'
$prUrl='https://github.com/MrGesier/SwarmTrading/pull/2'
foreach($required in @($python,$land,$watch)){if(-not(Test-Path -LiteralPath $required)){throw "Dependance absente : $required. Aucun merge effectue."}}
Set-Location -LiteralPath $repo
function Read-NativeJson([string]$Program,[string[]]$Arguments){
  $raw=& $Program @Arguments
  if($LASTEXITCODE -ne 0){throw (($raw -join "`n")+"`nVerification interrompue. Aucun contournement autorise.")}
  return (($raw -join "`n") | ConvertFrom-Json)
}
$pr=Read-NativeJson 'gh' @('pr','view',$prUrl,'--json','headRefOid,headRefName,baseRefName,state,url')
if($pr.state -eq 'MERGED'){Write-Host 'PR #2 deja fusionnee.';exit 0}
if($pr.state -ne 'OPEN' -or $pr.headRefName -ne 'darwin-demo-autocorrection-v3' -or $pr.baseRefName -ne 'darwin-v0.11-factory-evolution'){throw 'PR ou branches inattendues. Arret.'}
$sha=$pr.headRefOid
$planArgs=@($land,'--repo',$repo,'--pr',$prUrl,'--head',$sha,'--mode','auto','--method','merge')
$plan=Read-NativeJson $python $planArgs
if($plan.state -ne 'confirmation_required' -or -not $plan.readinessPolicyDigest){throw 'Plan de fusion non valide.'}
Write-Host "PR : $prUrl"
Write-Host "Source : $($pr.headRefName)"
Write-Host "Destination : $($pr.baseRefName) (PR #1 separee vers main)"
Write-Host "Commit exact : $sha"
Write-Host 'This landing request may merge the pull request immediately.'
Write-Host 'Cette demande peut fusionner la PR immediatement. Aucun deploiement ni activation du trading reel.'
if($VerifierSeulement){Write-Host 'Verification terminee. Aucune fusion demandee.';exit 0}
$answer=Read-Host "Pour approuver ce commit, saisir FUSIONNER $sha (Entree pour annuler)"
if($answer -cne "FUSIONNER $sha"){Write-Host 'Annule. Aucune fusion demandee.';exit 0}
$landed=Read-NativeJson $python ($planArgs+@('--policy-digest',$plan.readinessPolicyDigest,'--confirm'))
if($landed.state -ne 'landing_requested'){throw 'Fusion non confirmee par GitHub.'}
Write-Host 'Demande acceptee. Verification de la fusion effective...'
$result=Read-NativeJson $python @($watch,'--target',"$repo=$prUrl",'--await-merge',$sha,'--await-merge-mode','auto','--await-merge-since',$landed.requestedAt,'--timeout','180','--interval','10','--max-interval','30')
if($result.state -eq 'merged'){Write-Host "SUCCES : PR #2 fusionnee, commit $sha."}
else {Write-Host "Etat GitHub : $($result.state). Ne pas considerer la fusion comme terminee.";exit 1}
