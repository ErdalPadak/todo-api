param(
  [string]$Root = "http://127.0.0.1:9103",
  [string]$ApiKey,
  [switch]$RestartService
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

function Section($t){ Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function Info($t){ Write-Host $t -ForegroundColor Gray }
function Ok($t){ Write-Host $t -ForegroundColor Green }
function Warn($t){ Write-Host $t -ForegroundColor Yellow }
function Fail($t){ Write-Host $t -ForegroundColor Red }

# --- Header'lar (sadece x-api-key varsa ekle) ---
[hashtable]$HDR = @{}
if ($PSBoundParameters.ContainsKey('ApiKey') -and $ApiKey) {
  $HDR['x-api-key'] = $ApiKey
} elseif (Test-Path .\.apikey) {
  $HDR['x-api-key'] = (Get-Content .\.apikey -Raw).Trim()
}

# REST helper: Body hashtable ise JSON'a çevirir ve Content-Type'ı ayarlar
function IRX {
  param(
    [Parameter(Mandatory)] [ValidateSet('GET','POST','PATCH','DELETE')]
    [string]$Method,
    [Parameter(Mandatory)] [string]$Url,
    [object]$Body,
    [hashtable]$Headers
  )
  $sp = @{ Method=$Method; Uri=$Url; ErrorAction='Stop'; TimeoutSec=20 }

  if ($null -ne $Body) {
    if ($Body -is [string]) {
      $sp.Body = $Body
      if (-not $sp.ContainsKey('ContentType')) { $sp.ContentType = 'application/json' }
    } else {
      $sp.Body = ($Body | ConvertTo-Json -Depth 10)
      $sp.ContentType = 'application/json'
    }
  }
  if ($Headers -and $Headers.Count) { $sp.Headers = $Headers }
  Invoke-RestMethod @sp
}

# (İsteğe bağlı) servisi yeniden başlat
if ($RestartService) {
  Section "Servisi yeniden başlat"
  try {
    & nssm stop  todo-api-9103 2>$null | Out-Null
    & nssm start todo-api-9103 2>$null | Out-Null
    $t0 = Get-Date
    do {
      Start-Sleep -Milliseconds 300
      try { $health = IRX -Method GET -Url "$Root/health" -Headers $HDR } catch { $health = $null }
    } while (-not $health -and (New-TimeSpan $t0 (Get-Date)).TotalSeconds -lt 12)
    if ($health) { Ok ("HEALTH: " + ($health | ConvertTo-Json -Compress)) } else { Fail "Health gelmedi" }
  } catch { Fail $_.Exception.Message }
}

Section "HEALTH"
try {
  $h = IRX -Method GET -Url "$Root/health" -Headers $HDR
  Ok ("HEALTH: " + ($h | ConvertTo-Json -Compress))
} catch { Fail $_.Exception.Message }

Section "Mini CRUD Smoke"
try{
  # 422'yi önlemek için Body hashtable → JSON + Content-Type=application/json
  $c  = IRX -Method POST  -Url "$Root/tasks" -Body @{ title="smoke"; notes="e2e" } -Headers $HDR
  $id = $c.id
  Ok "CREATE id=$id"
  IRX -Method PATCH -Url "$Root/tasks/$id" -Body @{ done=$true } -Headers $HDR | Out-Null
  $g = IRX -Method GET -Url "$Root/tasks/$id" -Headers $HDR
  if ($g.done -eq $true) { Ok "PATCH/GET OK (done=true)" } else { Fail "PATCH doğrulanamadı" }
} catch { Fail $_.Exception.Message }

# Var ise mevcut smoke script'lerini de koştur
$rootDir    = (Resolve-Path ".").Path
$smokeE2E   = Join-Path $rootDir "scripts\smoke_e2e.ps1"
$smokeBatch = Join-Path $rootDir "scripts\smoke_batch.ps1"

if (Test-Path $smokeE2E) {
  Section "scripts\smoke_e2e.ps1"
  try { & powershell -NoProfile -ExecutionPolicy Bypass -File $smokeE2E -Root $Root } catch { Warn "smoke_e2e hata: $($_.Exception.Message)" }
} else { Warn "smoke_e2e.ps1 yok, mini smoke ile yetinildi." }

if (Test-Path $smokeBatch) {
  Section "scripts\smoke_batch.ps1"
  try { & powershell -NoProfile -ExecutionPolicy Bypass -File $smokeBatch -Root $Root } catch { Warn "smoke_batch hata: $($_.Exception.Message)" }
} else { Warn "smoke_batch.ps1 yok, batch testi atlandı." }

Section "EXPORT (CSV/JSONL) örnek"
try{
  $csv   = IRX -Method GET -Url "$Root/export?format=csv&limit=3&offset=0"   -Headers $HDR
  $jsonl = IRX -Method GET -Url "$Root/export?format=jsonl&limit=3&offset=0" -Headers $HDR
  Ok "--- CSV ---"
  $csv -split "`n" | Select-Object -First 5 | ForEach-Object { $_.TrimEnd() } | ForEach-Object { Write-Host $_ }
  Ok "`n--- JSONL ---"
  $jsonl -split "`n" | Select-Object -First 3 | ForEach-Object { $_.TrimEnd() } | ForEach-Object { Write-Host $_ }
} catch { Warn "Export denenemedi: $($_.Exception.Message)" }

Section "BİTTİ"
