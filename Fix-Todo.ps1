# ===== Todo API 500 Teşhis + Otomatik Onarım (PS 5.1) =====
$ErrorActionPreference = 'Stop'

$port = 9103
$root = "http://127.0.0.1:$port"
$dir  = "C:\maiq_demo\apps\todo_api"
$py   = "$env:MAIQ_HOME\.venv\Scripts\python.exe"
$uvi  = "$env:MAIQ_HOME\.venv\Scripts\uvicorn.exe"
$out  = Join-Path $dir "uvicorn_$port.out.log"
$errf = Join-Path $dir "uvicorn_$port.err.log"
$app  = Join-Path $dir "app.py"

if (-not (Test-Path $dir)) { throw "Klasör yok: $dir" }
Set-Location $dir

function Kill-Port {
  param([int]$Port)
  $procs = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)
  foreach ($procId in $procs) {
    try { taskkill /PID $procId /T /F | Out-Null } catch {}
  }
}

function Start-Uvicorn {
  Kill-Port -Port $port
  Remove-Item $out,$errf -ErrorAction SilentlyContinue
  $args = @("app:app","--host","127.0.0.1","--port",$port)
  $p = Start-Process $uvi -ArgumentList $args -WorkingDirectory $dir -PassThru `
       -RedirectStandardOutput $out -RedirectStandardError $errf
  "UVICORN PID: $($p.Id)"

  $ok = $false
  for ($i=0; $i -lt 30; $i++) {
    try { $null = (Invoke-RestMethod "$root/openapi.json").paths; $ok = $true; break } catch { Start-Sleep 0.3 }
  }
  if (-not $ok) {
    "PATHS:"; try { (Invoke-RestMethod "$root/openapi.json").paths.Keys } catch {}
    "---- uvicorn stderr tail ----"; if (Test-Path $errf) { Get-Content $errf -Tail 120 }
    throw "API ayağa kalkmadı."
  }
}

function Get-DbPath {
  if (-not (Test-Path $app)) { return (Join-Path $dir "todo.db") }
  $raw = Get-Content $app -Raw
  $m = [regex]::Match($raw, "connect\(\s*[rR]?['""](?<p>[^'""]+?\.db)['""]\s*\)")
  $db = if ($m.Success) { $m.Groups['p'].Value } else { "todo.db" }
  if (-not (Split-Path $db -IsAbsolute)) { $db = Join-Path $dir $db }
  return $db
}

function Ensure-DbSchema {
  $db = Get-DbPath
  $pycode = @"
import sqlite3, os
db = r'$db'
os.makedirs(os.path.dirname(db) or '.', exist_ok=True)
con = sqlite3.connect(db)
c = con.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS tasks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  description TEXT DEFAULT '',
  done INTEGER DEFAULT 0,
  tags TEXT DEFAULT '[]',
  due TEXT,
  created_at TEXT DEFAULT (datetime('now'))
)
""")
# kolon yoksa ekle
cols = [r[1] for r in c.execute("PRAGMA table_info(tasks)").fetchall()]
expected = [
 ("title", "TEXT"),
 ("description", "TEXT"),
 ("done", "INTEGER"),
 ("tags", "TEXT"),
 ("due", "TEXT"),
 ("created_at", "TEXT")
]
for name, decl in expected:
    if name not in cols:
        c.execute("ALTER TABLE tasks ADD COLUMN %s %s" % (name, decl))
con.commit(); con.close()
print("DB_OK", db)
"@
  $tmp = Join-Path $dir "_schema_fix.py"
  $pycode | Set-Content -LiteralPath $tmp -Encoding UTF8
  & $py $tmp | Out-Host
  Remove-Item $tmp -ErrorAction SilentlyContinue
}

function Resolve-TaskCreateSchema {
  try {
    $open = Invoke-RestMethod "$root/openapi.json"
  } catch { return @{} }
  $pathNode = $open.paths."/tasks"
  if (-not $pathNode) { return @{} }
  $post = $pathNode.post
  if (-not $post) { return @{} }
  $schema = $post.requestBody.content."application/json".schema
  if ($schema.'$ref') {
    $name = ($schema.'$ref' -split '/')[-1]
    $schema = $open.components.schemas.$name
  }
  $req = @()
  if ($schema.required) { $req = @($schema.required) }
  $props = @{}
  if ($schema.properties) {
    foreach ($k in $schema.properties.PSObject.Properties.Name) {
      $props[$k] = $schema.properties.$k.type
    }
  }
  return @{ required = $req; props = $props }
}

function Minimal-Body {
  $s = Resolve-TaskCreateSchema
  $req = if ($s.required) { $s.required } else { @() }
  $props = if ($s.props) { $s.props } else { @{} }
  $body = @{}
  foreach ($name in $req) {
    $t = $props[$name]
    if ($t -eq "string" -or -not $t) { $body[$name] = "demo" }
    elseif ($t -eq "integer") { $body[$name] = 0 }
    elseif ($t -eq "boolean") { $body[$name] = $false }
    elseif ($t -eq "array") { $body[$name] = @() }
    else { $body[$name] = "demo" }
  }
  if (-not $body.ContainsKey("title")) { $body["title"] = "demo" }
  return ($body | ConvertTo-Json)
}

# 1) Başlat
Start-Uvicorn
"PATHS:"; (Invoke-RestMethod "$root/openapi.json").paths.Keys | Sort-Object
"`n/where:"; Invoke-RestMethod "$root/where" | Format-List

# 2) Body hazırla
$body = Minimal-Body
"BODY -> $body"

# 3) POST /tasks; 500 ise DB fix + retry
try {
  $task = Invoke-RestMethod -Method Post "$root/tasks" -ContentType 'application/json' -Body $body
} catch {
  "POST /tasks hata; stderr tail:"
  if (Test-Path $errf) { Get-Content $errf -Tail 200 | Out-Host }
  $tail = if (Test-Path $errf) { (Get-Content $errf -Tail 200) -join "`n" } else { "" }
  if ($tail -match 'no such table:\s*tasks' -or $tail -match 'has no column named') {
    "→ DB şeması sorunlu; migrasyon uygulanıyor..."
    Ensure-DbSchema
    Start-Uvicorn
    $task = Invoke-RestMethod -Method Post "$root/tasks" -ContentType 'application/json' -Body $body
  } else {
    throw
  }
}

"id=$($task.id)"
"BEFORE DONE: $($task.done)"

# 4) PATCH /tasks/{id} -> done=true
$null  = Invoke-RestMethod -Method Patch "$root/tasks/$($task.id)" -ContentType 'application/json' `
         -Body (@{done=$true} | ConvertTo-Json)
$after = Invoke-RestMethod "$root/tasks/$($task.id)"
"AFTER  DONE: $($after.done)"

# 5) done=true liste & metrics
try {
  $doneList = Invoke-RestMethod "$root/tasks?done=true&limit=5&offset=0"
  "DONE LIST COUNT: $($doneList.Count)"
} catch { "DONE LIST alınamadı: $($_.Exception.Message)" }
$metrics = Invoke-RestMethod "$root/metrics"
"METRICS: $($metrics | ConvertTo-Json -Compress)"
