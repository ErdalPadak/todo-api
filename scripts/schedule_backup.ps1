param(
  [string]$RepoDir = (Resolve-Path ".").Path,
  [string]$Root    = 'http://127.0.0.1:9103',
  [string]$Time    = '02:00',   # HH:mm
  [string]$ApiKey  = ''
)

$taskName = "todo-api daily backup"
$backupScript = Join-Path $RepoDir 'scripts\backup_job.ps1'
if(-not (Test-Path $backupScript)){ throw "Backup script bulunamadı: $backupScript" }

# Argümanları düzgün kaçışla
$cmd = 'powershell -NoProfile -ExecutionPolicy Bypass -File "{0}" -Root "{1}" -RepoDir "{2}"' -f $backupScript, $Root, $RepoDir
if($ApiKey -and $ApiKey.Trim().Length -gt 0){ $cmd += ' -ApiKey "{0}"' -f $ApiKey.Trim() }

schtasks /Create /TN "$taskName" /TR "$cmd" /SC DAILY /ST $Time /RL HIGHEST /F | Out-Null
Write-Host "Scheduled: $taskName @ $Time"
Write-Host "Komut: $cmd"
