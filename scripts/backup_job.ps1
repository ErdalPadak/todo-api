param(
  [string]$Root        = "http://127.0.0.1:9103",
  [string]$RepoDir     = (Resolve-Path ".").Path,
  [string]$ServiceName = "todo-api-9103",
  [int]$KeepDays       = 14,
  [string]$ApiKey      = ""
)

$ErrorActionPreference = 'Stop'

function IRX {
  param([string]$Method,[string]$Url,[hashtable]$Headers=$null,[string]$ContentType=$null,[string]$InFile=$null,[int]$TimeoutSec=15)
  $s = @{ Method=$Method; Uri=$Url; TimeoutSec=$TimeoutSec }
  if($Headers){ $s.Headers = $Headers }
  if($ContentType){ $s.ContentType = $ContentType }
  if($InFile){ $s.InFile = $InFile }
  try { return Invoke-RestMethod @s } catch { return $null }
}
function WRX {
  param([string]$Url,[hashtable]$Headers=$null,[int]$TimeoutSec=15)
  $s = @{ Method='GET'; Uri=$Url; TimeoutSec=$TimeoutSec; UseBasicParsing=$true }
  if($Headers){ $s.Headers = $Headers }
  try { return (Invoke-WebRequest @s).Content } catch { return $null }
}
function Stop-ServiceIfExists([string]$Name){
  $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
  if($svc -and $svc.Status -eq 'Running'){
    try { & nssm stop $Name 2>$null | Out-Null } catch {}
    Start-Sleep -Seconds 2
    return $true
  }
  return $false
}
function Start-ServiceIfExists([string]$Name){
  $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
  if($svc){ try { & nssm start $Name 2>$null | Out-Null } catch {} }
}

$backups = Join-Path $RepoDir 'backups'
if(-not (Test-Path $backups)){ New-Item -ItemType Directory -Path $backups | Out-Null }
$ts = (Get-Date).ToString('yyyyMMdd_HHmmss')

$H = $null
if($ApiKey -and $ApiKey.Trim().Length -gt 0){ $H = @{ 'x-api-key' = $ApiKey.Trim() } }

# 1) Sağlık kontrolü (opsiyonel)
$health = IRX -Method GET -Url "$Root/health" -Headers $H
$apiUp = $false
if($health -and $health.status -eq 'healthy'){ $apiUp = $true }

# 2) Export (API ayaktaysa)
$csvPath   = $null
$jsonlPath = $null
if($apiUp){
  $csvPath   = Join-Path $backups ("export_" + $ts + ".csv")
  $jsonlPath = Join-Path $backups ("export_" + $ts + ".jsonl")

  $csv = WRX -Url "$Root/export?format=csv&limit=100000&offset=0" -Headers $H
  if($csv){ $csv | Out-File -FilePath $csvPath -Encoding utf8 }

  $jsonl = WRX -Url "$Root/export?format=jsonl&limit=100000&offset=0" -Headers $H
  if($jsonl){ $jsonl | Out-File -FilePath $jsonlPath -Encoding utf8 }
} else {
  Write-Warning "API kapalı/yetişilemiyor → export atlandı (DB yedeği alınacak)."
}

# 3) DB dosyası yedeği (gerekirse servis kısa durdurulup kopyalanır)
$dbPath = Join-Path $RepoDir 'todo.db'
$dbBackup = $null
if(Test-Path $dbPath){
  $restarted = $false
  $stopped = $false
  try {
    # İlk deneme: servis durdurmadan kopyala (kilit yoksa geçer)
    $dbBackup = Join-Path $backups ("todo_" + $ts + ".db")
    Copy-Item $dbPath $dbBackup -Force
  } catch {
    # Kilit olabilir → durdur, kopyala, tekrar başlat
    $stopped = Stop-ServiceIfExists $ServiceName
    Copy-Item $dbPath $dbBackup -Force
    if($stopped){ Start-ServiceIfExists $ServiceName; $restarted = $true }
  }
}

# 4) Rotasyon
$cutoff = (Get-Date).AddDays(-$KeepDays)
Get-ChildItem -Path $backups -File | Where-Object { $_.LastWriteTime -lt $cutoff } | Remove-Item -Force

Write-Host "BACKUP OK"
if($csvPath   -and (Test-Path $csvPath))   { Write-Host " CSV   : $csvPath" }
if($jsonlPath -and (Test-Path $jsonlPath)) { Write-Host " JSONL : $jsonlPath" }
if($dbBackup)                               { Write-Host " DB    : $dbBackup" }
