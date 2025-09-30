param(
  [string]$Root = "http://127.0.0.1:9103",
  [switch]$TryReinstall
)

function Test-Port {
  param([string]$HostName, [int]$Port, [int]$TimeoutMs = 1500)
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $iar = $c.BeginConnect($HostName, $Port, $null, $null)
    $ok  = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
    if ($ok) { $c.EndConnect($iar) }
    $ok = $ok -and $c.Connected
    $c.Close()
    return $ok
  } catch { return $false }
}

# 1) Port erişilebilir mi?
$uri = [Uri]$Root
$portOk = Test-Port $uri.DnsSafeHost $uri.Port
"Port reachability: $portOk"

# 2) Health denemesi
$health = $null
try {
  $health = Invoke-RestMethod "$Root/health" -TimeoutSec 5
  "HEALTH: " + ($health | ConvertTo-Json -Compress)
} catch {
  "HEALTH: FAILED"
}

# 3) Gerekirse servis kurulumunu dene (-TryReinstall ile)
if (-not $health -and $TryReinstall.IsPresent) {
  $svc = Get-Service -Name 'todo-api-9103' -ErrorAction SilentlyContinue
  if (-not $svc) {
    $installer = Join-Path $PSScriptRoot 'scripts\svc_install.ps1'
    if (Test-Path $installer) {
      "Installing service via: $installer"
      powershell -NoProfile -ExecutionPolicy Bypass -File $installer
      Start-Sleep -Seconds 2
      try {
        $health = Invoke-RestMethod "$Root/health" -TimeoutSec 5
        "HEALTH -> " + ($health | ConvertTo-Json -Compress)
      } catch { "HEALTH still not reachable." }
    } else {
      Write-Warning "Installer not found: $installer"
    }
  }
}

# 4) Mini CRUD smoke (bağımsız)
try {
  "CREATE id=" + (
    Invoke-RestMethod -Method Post "$Root/tasks" -ContentType 'application/json' `
      -Body (@{ title='diag-mini'; notes='e2e' } | ConvertTo-Json)
  ).id

  $last = Invoke-RestMethod -Method Post "$Root/tasks" -ContentType 'application/json' `
    -Body (@{ title='diag-mini-2'; notes='e2e' } | ConvertTo-Json)

  Invoke-RestMethod -Method Patch "$Root/tasks/$($last.id)" -ContentType 'application/json' `
    -Body (@{ done = $true } | ConvertTo-Json) | Out-Null

  $g = Invoke-RestMethod "$Root/tasks/$($last.id)"
  "PATCH/GET OK (done=$($g.done))"
} catch {
  Write-Warning "Mini CRUD smoke failed: $($_.Exception.Message)"
}

# 5) Eğer varsa mevcut smoke scriptlerini de çalıştır (opsiyonel)
$e2e = Join-Path $PSScriptRoot 'scripts\smoke_e2e.ps1'
if (Test-Path $e2e) {
  "`n=== scripts\smoke_e2e.ps1 ==="
  powershell -NoProfile -ExecutionPolicy Bypass -File $e2e -Root $Root
}

$batch = Join-Path $PSScriptRoot 'scripts\smoke_batch.ps1'
if (Test-Path $batch) {
  "`n=== scripts\smoke_batch.ps1 ==="
  powershell -NoProfile -ExecutionPolicy Bypass -File $batch -Root $Root
}
