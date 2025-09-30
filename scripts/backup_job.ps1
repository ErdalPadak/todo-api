param(
  [string]$RepoDir = "C:\maiq_demo\apps\todo_api",
  [string]$Root    = "http://127.0.0.1:9103",
  [string]$ApiKey  = ""
)

function New-Stamp { (Get-Date).ToString("yyyyMMdd_HHmmss") }
function Ensure-Dir($p){ if(-not (Test-Path $p)){ New-Item -ItemType Directory -Path $p | Out-Null } }

# ---------- Ortak Hazırlık ----------
$stamp     = New-Stamp
$backupDir = Join-Path $RepoDir "backups"
Ensure-Dir $backupDir
$H = @{}
if($ApiKey -and $ApiKey.Trim().Length -gt 0){ $H["x-api-key"] = $ApiKey.Trim() }

# ---------- Parçalı Export Yardımcıları ----------
function Invoke-ExportPaged {
  param(
    [ValidateSet("jsonl","csv")] [string]$Format,
    [string]$OutFile
  )
  $limits = @(200,100,50)   # 422 olursa sıradaki küçük limit denenir
  $offset = 0
  $isFirstChunk = $true
  $tmp = [IO.Path]::GetTempFileName()

  while ($true) {
    $chunkDownloaded = $false
    foreach($limit in $limits){
      $url = "$Root/export?format=$Format&limit=$limit&offset=$offset"
      try{
        Invoke-WebRequest -Uri $url -Headers $H -UseBasicParsing -OutFile $tmp
        $chunkDownloaded = $true
        break
      } catch {
        # 422 gibi hatalarda bir sonraki küçük limit denenir
        continue
      }
    }

    if(-not $chunkDownloaded){
      Write-Warning "Export ($Format) parçayı indiremedim (offset=$offset). Durduruluyor."
      break
    }

    $lines = @()
    try { $lines = Get-Content -Path $tmp -ErrorAction Stop } catch { $lines = @() }

    if($Format -eq 'jsonl'){
      $rowCount = $lines.Count
      if($rowCount -eq 0){ break }
      # JSONL: doğrudan ekle
      Add-Content -Path $OutFile -Value $lines
      # limit tahmini: rowCount < max($limits) olursa bitti kabul ederiz
      if($rowCount -lt ($limits | Measure-Object -Maximum | Select-Object -ExpandProperty Maximum)){ break }
      $offset += $rowCount
    } else {
      # CSV: başlık + satırlar
      if($lines.Count -eq 0){ break }
      if($isFirstChunk){
        Add-Content -Path $OutFile -Value $lines
        $dataCount = [Math]::Max($lines.Count - 1, 0)
        $isFirstChunk = $false
      } else {
        # başlığı atla
        if($lines.Count -gt 1){
          Add-Content -Path $OutFile -Value ($lines | Select-Object -Skip 1)
        }
        $dataCount = [Math]::Max($lines.Count - 1, 0)
      }
      if($dataCount -lt ($limits | Measure-Object -Maximum | Select-Object -ExpandProperty Maximum)){ break }
      $offset += $dataCount
    }
  }

  Remove-Item -Force -ErrorAction SilentlyContinue $tmp
}

# ---------- 1) JSONL export (paginated) ----------
try {
  $outJsonl = Join-Path $backupDir ("tasks_{0}.jsonl" -f $stamp)
  if(Test-Path $outJsonl){ Remove-Item -Force $outJsonl }
  Invoke-ExportPaged -Format jsonl -OutFile $outJsonl
  Write-Host "JSONL export => $outJsonl"
} catch { Write-Warning "JSONL export başarısız: $($_.Exception.Message)" }

# ---------- 2) CSV export (paginated) ----------
try {
  $outCsv = Join-Path $backupDir ("tasks_{0}.csv" -f $stamp)
  if(Test-Path $outCsv){ Remove-Item -Force $outCsv }
  Invoke-ExportPaged -Format csv -OutFile $outCsv
  Write-Host "CSV export   => $outCsv"
} catch { Write-Warning "CSV export başarısız: $($_.Exception.Message)" }

# ---------- 3) .db dosyası kopyası ----------
try {
  $db = Get-ChildItem -Path $RepoDir -Filter *.db -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if($db){
    $outDb = Join-Path $backupDir ("todo_{0}.db" -f $stamp)
    Copy-Item -Path $db.FullName -Destination $outDb -Force
    Write-Host "DB backup    => $outDb (kaynak: $($db.Name))"
  } else {
    Write-Warning "Kopyalanacak *.db bulunamadı (RepoDir: $RepoDir)."
  }
} catch { Write-Warning "DB kopyası başarısız: $($_.Exception.Message)" }

# ---------- 4) Health ----------
try {
  $health = Invoke-RestMethod -Uri "$Root/health" -Headers $H -TimeoutSec 5
  Write-Host ("HEALTH: " + ($health | ConvertTo-Json -Compress))
} catch { Write-Warning "Health kontrolü alınamadı: $($_.Exception.Message)" }
