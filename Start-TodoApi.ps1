param(
  [int]$Port = 9103
)

$ErrorActionPreference = 'Stop'
$dir = "C:\maiq_demo\apps\todo_api"
$uvi = "$env:MAIQ_HOME\.venv\Scripts\uvicorn.exe"
$out = Join-Path $dir "uvicorn_$Port.out.log"
$err = Join-Path $dir "uvicorn_$Port.err.log"
$root = "http://127.0.0.1:$Port"

if (-not (Test-Path $dir)) { throw "Klasör yok: $dir" }
Set-Location $dir

# Portu boşalt
$pids = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
          Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($p in $pids) { try { taskkill /PID $p /T /F | Out-Null } catch {} }

Remove-Item $out,$err -ErrorAction SilentlyContinue

# Uvicorn'u başlat
$args = @("app:app","--host","127.0.0.1","--port",$Port)
$proc = Start-Process $uvi -ArgumentList $args -WorkingDirectory $dir -PassThru `
        -RedirectStandardOutput $out -RedirectStandardError $err
"UVICORN PID: $($proc.Id)"

# OpenAPI poll
$ok = $false
for ($i=0; $i -lt 40; $i++) {
  try { $paths = (Invoke-RestMethod "$root/openapi.json").paths.Keys; $ok = $true; break } catch { Start-Sleep 0.25 }
}
"PATHS:"; if ($ok) { $paths } else { "OpenAPI alınamadı"; if (Test-Path $err) { Get-Content $err -Tail 120 } }
if (-not $ok) { throw "API ayağa kalkmadı." }

# where
"`n/where:`n"
try { Invoke-RestMethod "$root/where" | Format-List } catch { "where yok (opsiyonel)" }
