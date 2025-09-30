param(
  [string]$Root = 'http://127.0.0.1:9103',
  [string]$ApiKey = ''
)

function Invoke-Http {
  param([string]$Method,[string]$Uri,[string]$Body = $null,[hashtable]$Headers = @{})
  try {
    $sp = @{ Method=$Method; Uri=$Uri; Headers=$Headers; ContentType='application/json' }
    if ($Body) { $sp['Body'] = $Body }
    $r = Invoke-RestMethod @sp -ErrorAction Stop
    return @{ ok=$true; status=200; body=$r }
  } catch {
    $we = $_.Exception
    $status = 0
    $content = ''
    if ($we.Response) {
      try {
        $status = [int]$we.Response.StatusCode.value__
      } catch {}
      try {
        $sr = New-Object System.IO.StreamReader($we.Response.GetResponseStream())
        $content = $sr.ReadToEnd()
        $sr.Dispose()
      } catch {}
    }
    return @{ ok=$false; status=$status; raw=$content }
  }
}

$H = @{}
if ($ApiKey) { $H['x-api-key'] = $ApiKey }

Write-Host "HEALTH:"
Invoke-RestMethod "$Root/health" | ConvertTo-Json -Compress

# Hazırlık: 2 kayıt
$payload = @{ title='batch-demo-1'; notes='demo' } | ConvertTo-Json -Compress
$id1 = (Invoke-RestMethod -Method Post "$Root/tasks" -Headers $H -ContentType 'application/json' -Body $payload).id
$payload = @{ title='batch-demo-A'; notes='demo' } | ConvertTo-Json -Compress
$id2 = (Invoke-RestMethod -Method Post "$Root/tasks" -Headers $H -ContentType 'application/json' -Body $payload).id
Write-Host "Created: id1=$id1 id2=$id2"

# non-atomic
$ops = @{ ops = @(
  @{ op='patch'; id=$id1; set=@{ done=$true } },
  @{ op='delete'; id=$id2 },
  @{ op='delete'; id=99999999 }
)} | ConvertTo-Json -Depth 6 -Compress

$rNA = Invoke-Http -Method 'POST' -Uri "$Root/batch?atomic=false" -Body $ops -Headers $H
"NON-ATOMIC RESULT (status=$($rNA.status)):"
if ($rNA.ok) {
  $rNA.body | ConvertTo-Json -Depth 6
} else {
  $rNA.raw
}
"VERIFY NON-ATOMIC: id1.done=" + (Invoke-RestMethod "$Root/tasks/$id1" -Headers $H -ErrorAction SilentlyContinue).done + "  id2.deleted=" + ((Invoke-RestMethod "$Root/tasks/$id2" -Headers $H -ErrorAction SilentlyContinue).id -eq $null)

# atomic
$ops2 = @{ ops = @(
  @{ op='patch'; id=$id1; set=@{ done=$false } },
  @{ op='delete'; id=99999999 }
)} | ConvertTo-Json -Depth 6 -Compress

$rAT = Invoke-Http -Method 'POST' -Uri "$Root/batch?atomic=true" -Body $ops2 -Headers $H
"ATOMIC RESULT (status=$($rAT.status)):"
if ($rAT.ok) {
  $rAT.body | ConvertTo-Json -Depth 6
} else {
  $rAT.raw
}
"VERIFY ATOMIC (rollback): id1.done=" + (Invoke-RestMethod "$Root/tasks/$id1" -Headers $H).done
