$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath($PSScriptRoot)
$branch='darwin-demo-autocorrection-v3'
$base='darwin-v0.11-factory-evolution'
$remote='MrGesier/SwarmTrading'
function Run-Native([string]$Program,[string[]]$Arguments){
  if($Program -eq 'git'){$Arguments=@('-c',('safe.directory='+$repo.Replace('\','/')))+$Arguments}
  $previous=$ErrorActionPreference
  try{$ErrorActionPreference='Continue'; & $Program @Arguments; $code=$LASTEXITCODE}finally{$ErrorActionPreference=$previous}
  if($code -ne 0){throw "Echec de $Program (code $code). Aucun force-push ni fusion."}
}
Set-Location -LiteralPath $repo
if((Run-Native git @('branch','--show-current')).Trim() -ne $branch){throw 'Branche inattendue.'}
if(Run-Native git @('status','--porcelain')){throw 'Modifications non commitees : publication interrompue.'}
if((Run-Native git @('remote','get-url','origin')).Trim() -ne "https://github.com/$remote.git"){throw 'Depot distant inattendu.'}
$ghCommand=Get-Command gh -ErrorAction SilentlyContinue
$gh=if($ghCommand){$ghCommand.Source}else{Join-Path $env:ProgramFiles 'GitHub CLI\gh.exe'}
Run-Native $gh @('auth','status','--hostname','github.com')
$env:PATH=(Split-Path -Parent $gh)+[IO.Path]::PathSeparator+$env:PATH
$gitAuth=@('-c','credential.helper=','-c','credential.helper=!gh auth git-credential')
Run-Native git ($gitAuth+@('fetch','origin',$base))
Run-Native git @('merge-base','--is-ancestor',('origin/'+$base),'HEAD')
$sha=(Run-Native git @('rev-parse','HEAD')).Trim()
Run-Native git ($gitAuth+@('push','origin',('HEAD:refs/heads/'+$branch)))
$remoteLine=(Run-Native git ($gitAuth+@('ls-remote','origin',('refs/heads/'+$branch)))) -join ''
if(($remoteLine -split '\s+')[0] -ne $sha){throw 'Commit distant different du commit local.'}
$prs=((Run-Native $gh @('pr','list','--repo',$remote,'--head',$branch,'--base',$base,'--state','open','--json','number,url')) -join "`n") | ConvertFrom-Json
$body=Join-Path $repo 'PR_V3.md'
$title='Darwin: Hyperliquid paper, async LLM research and reviewed code proposals'
if(@($prs).Count){
  Run-Native $gh @('pr','edit',[string]$prs[0].number,'--repo',$remote,'--title',$title,'--body-file',$body)
  Write-Host $prs[0].url
}else{
  Run-Native $gh @('pr','create','--repo',$remote,'--head',$branch,'--base',$base,'--draft','--title',$title,'--body-file',$body)
}
Write-Host "Publication verifiee : $sha. PR de demonstration, aucune fusion."
