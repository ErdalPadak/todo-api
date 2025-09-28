param([string]$Root='http://127.0.0.1:9103')
$ErrorActionPreference='Stop'

function Pass($m){ Write-Host ("PASS  " + $m) }
function Fail($m){ Write-Host ("FAIL  " + $m); exit 1 }

function Try-Req([string]$Method,[string]$Url,$Body=$null){
  try{
    if($null -ne $Body){
      $json = ($Body | ConvertTo-Json -Depth 10)
      $r = Invoke-RestMethod -Method $Method -Uri $Url -ContentType 'application/json' -Headers @{Accept='application/json'} -Body $json
    } else {
      $r = Invoke-RestMethod -Method $Method -Uri $Url -Headers @{Accept='application/json'}
    }
    return @{ ok=$true; data=$r; status=200 }
  } catch {
    $code = $null
    try { $code = $_.Exception.Response.StatusCode.value__ } catch {}
    return @{ ok=$false; err=$_; status=$code }
  }
}

# 1) Health
$r = Try-Req GET "$Root/health"
if(-not $r.ok){ Fail "GET /health -> $($r.status)" } else { Pass "GET /health" }

# 2) Create
$title = "smoke-e2e-{0:yyyyMMdd-HHmmss}" -f (Get-Date)
$r = Try-Req POST "$Root/tasks" @{ title=$title; notes="e2e" }
if(-not $r.ok){ Fail "POST /tasks -> $($r.status)" }
$id = $r.data.id
if(-not $id){ Fail "POST /tasks -> id yok" } else { Pass "POST /tasks id=$id" }

# 3) Patch done=true
$r = Try-Req PATCH "$Root/tasks/$id" @{ done=$true }
if(-not $r.ok){ Fail "PATCH /tasks/$id -> $($r.status)" } else { Pass "PATCH /tasks/$id done=true" }

# 4) Get by id ve doğrula
$r = Try-Req GET "$Root/tasks/$id"
if(-not $r.ok){ Fail "GET /tasks/$id -> $($r.status)" }
elseif(-not $r.data.done){ Fail "GET /tasks/$id -> done!=true" }
else { Pass "GET /tasks/$id done=true OK" }

# 5) List (limit<=200)
$r = Try-Req GET "$Root/tasks?limit=50&offset=0"
if(-not $r.ok){ Fail "GET /tasks list -> $($r.status)" } else { Pass "GET /tasks?limit=50&offset=0" }

# 6) Negatif: limit>200 => 422
$r = Try-Req GET "$Root/tasks?limit=500&offset=0"
if($r.ok -or $r.status -ne 422){ Fail "GET /tasks?limit=500 -> 422 bekleniyordu, geldi $($r.status)" }
else { Pass "GET /tasks?limit=500 => 422 (beklenen)" }

# 7) Metrics
$r = Try-Req GET "$Root/metrics"
if(-not $r.ok){ Fail "GET /metrics -> $($r.status)" }
else { Pass ("GET /metrics " + ($r.data | ConvertTo-Json -Compress)) }

# 8) Mini pagination duman testi (0..19)
$bad = 0
for($o=0;$o -lt 20;$o++){
  $rr = Try-Req GET "$Root/tasks?limit=1&offset=$o"
  if(-not $rr.ok){ $bad++ ; Write-Host ("WARN offset " + $o + " -> " + $rr.status) }
}
if($bad -gt 0){ Fail "Pagination (0..19) hatalı: $bad" } else { Pass "Pagination (0..19) OK" }

Write-Host "E2E SMOKE: OK"
