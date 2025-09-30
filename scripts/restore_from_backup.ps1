param(
  [Parameter(Mandatory=$true)][string]$BackupDbPath,
  [string]$RepoDir     = (Resolve-Path ".").Path,
  [string]$ServiceName = "todo-api-9103",
  [string]$Root        = "http://127.0.0.1:9103"
)

$ErrorActionPreference = 'Stop'

function Stop-ServiceIfExists([string]$Name){
  $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
  if($svc){
    try { & nssm stop $Name 2>$null | Out-Null } catch {}
    Start-Sleep -Seconds 2
    return $true
  }
  return $false
}
function Start-ServiceIfExists([string]$Name){
  $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
  if($svc){
    try { & nssm start $Name 2>$null | Out-Null } catch {}
  }
}

if(-not (Test-Path $BackupDbPath)){ throw "Yedek DB bulunamadı: $BackupDbPath" }

$dbPath = Join-Path $RepoDir 'todo.db'
$bkDir  = Join-Path $RepoDir 'backups'
if(-not (Test-Path $bkDir)){ New-Item -ItemType Directory -Path $bkDir | Out-Null }
$ts = (Get-Date).ToString('yyyyMMdd_HHmmss')
$pre = Join-Path $bkDir ("restore_pre_" + $ts + ".db")

$wasRunning = Stop-ServiceIfExists $ServiceName

if(Test-Path $dbPath){ Copy-Item $dbPath $pre -Force }
Copy-Item $BackupDbPath $dbPath -Force

Start-ServiceIfExists $ServiceName
Start-Sleep -Seconds 2

# API varsa doğrula; yoksa atla
try {
  $h = Invoke-RestMethod "$Root/health" -TimeoutSec 8
  if($h.status -ne 'healthy'){ Write-Warning "Restore sonrası health beklenen değil: $($h | ConvertTo-Json -Compress)" }
} catch {
  Write-Warning "Restore sonrası health kontrolü yapılamadı (API kapalı olabilir): $($_.Exception.Message)"
}

Write-Host "RESTORE OK"
Write-Host " Eski DB yedeği: $pre"
Write-Host " Aktif DB      : $dbPath"
