param(
  [string]$Root = "http://127.0.0.1:9103"
)
$ErrorActionPreference = "Stop"

# API key: env veya .\.apikey
$script:APIKEY = $env:TODO_API_KEY
if(-not $script:APIKEY -and (Test-Path ".\.apikey")) {
  $script:APIKEY = (Get-Content ".\.apikey" -Raw).Trim()
}
function Get-ApiHeaders {
  if([string]::IsNullOrWhiteSpace($script:APIKEY)) { return @{} }
  return @{ "x-api-key" = $script:APIKEY }
}
function IRX($Method,$Url,[string]$Body,$ContentType) {
  try {
    $args = @{ Method=$Method; Uri=$Url; Headers=(Get-ApiHeaders); TimeoutSec=10 }
    if($Body) { $args.ContentType = $ContentType; $args.Body = $Body }
    $resp = Invoke-RestMethod @args
    return @{ ok=$true; status=200; body=$resp }
  } catch {
    $we = $_.Exception
    $status = 0
    try { $status = [int]$we.Response.StatusCode } catch {}
    $bodyText = $null
    try {
      $stream = $we.Response.GetResponseStream()
      if($stream) { $sr = New-Object IO.StreamReader($stream); $bodyText = $sr.ReadToEnd(); $sr.Close() }
    } catch {}
    return @{ ok=$false; status=$status; body=$bodyText }
  }
}

Write-Host "HEALTH:"
$h = IRX GET "$Root/health" $null $null
if(-not $h.ok){ throw "Health failed: $($h.status) $($h.body)" }
Write-Host ($h.body | ConvertTo-Json -Compress)

# Create two tasks
$r1 = IRX POST "$Root/tasks" (@{title="batch-demo-1"; notes="demo"} | ConvertTo-Json) 'application/json'
$r2 = IRX POST "$Root/tasks" (@{title="batch-demo-2"; notes="demo"} | ConvertTo-Json) 'application/json'
$id1 = $r1.body.id; $id2 = $r2.body.id
Write-Host ("Created: id1={0} id2={1}" -f $id1,$id2)

# Non-atomic batch
$opsNA = @{ ops = @(
  @{ op="patch"; id=$id1; set=@{ done=$true } },
  @{ op="delete"; id=$id2 },
  @{ op="delete"; id=99999999 }
)} | ConvertTo-Json -Depth 6
$na = IRX POST "$Root/batch?atomic=false" $opsNA 'application/json'
Write-Host "NON-ATOMIC RESULT:" ($na.body | ConvertTo-Json -Compress)

# Verify non-atomic
$v1 = IRX GET "$Root/tasks/$id1" $null $null
$done1 = $false; if($v1.ok){ $done1 = [bool]$v1.body.done }
$v2 = IRX GET "$Root/tasks/$id2" $null $null
$deleted2 = ($v2.status -eq 404)
Write-Host ("VERIFY NON-ATOMIC: id1.done={0}  id2.deleted={1}" -f $done1,$deleted2)

# Atomic batch (should rollback on error)
$r3 = IRX POST "$Root/tasks" (@{title="batch-demo-A"; notes="demo"} | ConvertTo-Json) 'application/json'
$idA = $r3.body.id
$opsAT = @{ ops = @(
  @{ op="patch"; id=$idA; set=@{ done=$true } },
  @{ op="delete"; id=99999999 }
)} | ConvertTo-Json -Depth 6
$at = IRX POST "$Root/batch?atomic=true" $opsAT 'application/json'
Write-Host "ATOMIC RESULT:" ($at | ConvertTo-Json -Compress)

# Verify rollback
$vA = IRX GET "$Root/tasks/$idA" $null $null
$doneA = $null
if($vA.ok){ $doneA = [bool]$vA.body.done }
Write-Host ("VERIFY ATOMIC (rollback): idA.done={0}" -f $doneA)

