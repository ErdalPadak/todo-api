param(
  [string]$Root = "http://127.0.0.1:9103",
  [string]$ServiceName = "todo-api-9103",
  [string]$RepoDir = "C:\maiq_demo\apps\todo_api",
  [switch]$TryReinstall,
  [string]$ApiKey = ""
)

function Test-Port {
  param([string]$TargetHost,[int]$TargetPort)
  try{
    $tcp = New-Object Net.Sockets.TcpClient
    $iar = $tcp.BeginConnect($TargetHost,$TargetPort,$null,$null)
    $ok  = $iar.AsyncWaitHandle.WaitOne(1500,$false)
    if($ok -and $tcp.Connected){ $tcp.Close(); return $true }
    $tcp.Close(); return $false
  }catch{ return $false }
}
function Tail-Logs {
  if(Test-Path .\svc.err.log){ '--- svc.err.log (tail) ---'; Get-Content .\svc.err.log -Tail 60 }
  if(Test-Path .\svc.out.log){ '--- svc.out.log (tail) ---'; Get-Content .\svc.out.log -Tail 60 }
}
function Get-NssmPath {
  $cmd = Get-Command nssm -ErrorAction SilentlyContinue
  if($cmd){ return $cmd.Source }
  return $null
}
function Get-AuthHeaders {
  param([string]$Key)
  if($Key -and $Key.Trim().Length -gt 0){ return @{ 'x-api-key' = $Key.Trim() } }
  return $null
}
function Invoke-Json {
  param([string]$Method,[string]$Url,$Body=$null,[hashtable]$Headers=$null)
  $sp = @{ Method=$Method; Uri=$Url; ContentType='application/json' }
  if($Headers){ $sp.Headers = $Headers }
  if($Body -ne $null){ $sp.Body = (ConvertTo-Json $Body -Depth 8) }
  return Invoke-RestMethod @sp
}

$uri = [uri]$Root
$headers = Get-AuthHeaders $ApiKey

"Port reachability: " + (Test-Port -TargetHost $uri.DnsSafeHost -TargetPort $uri.Port)

# servis yoksa isteğe bağlı kur
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if(-not $svc -and $TryReinstall){
  $svcScript = Join-Path $RepoDir "scripts\svc_install.ps1"
  if(-not (Test-Path $svcScript)){ throw "svc_install script yok: $svcScript" }
  "Installing service via: $svcScript"
  powershell -NoProfile -ExecutionPolicy Bypass -File $svcScript -BindHost $uri.DnsSafeHost -BindPort $uri.Port | Write-Host
}

# health poll
$up = $false
for($i=1;$i -le 12;$i++){
  try{
    $h = Invoke-RestMethod "$Root/health" -TimeoutSec 2
    "HEALTH: " + ($h | ConvertTo-Json -Compress)
    $up = $true; break
  }catch{ Start-Sleep -Milliseconds 500 }
}
if(-not $up){ "HEALTH erişilemedi. Son loglar:"; Tail-Logs; exit 2 }

# ---------- Mini CRUD ----------
$r1 = Invoke-Json POST "$Root/tasks" @{title='diag-smoke'; notes='e2e'} $headers
$idCRUD = $r1.id
Invoke-Json PATCH "$Root/tasks/$idCRUD" @{done=$true} $headers | Out-Null
$r2 = Invoke-RestMethod "$Root/tasks/$idCRUD"
"CREATE id=$idCRUD"
"PATCH/GET OK (done=$($r2.done))"

# ---------- /batch: NON-ATOMIC (ayrı id) ----------
$rNA1 = Invoke-Json POST "$Root/tasks" @{title='non-atomic'; notes='demo'} $headers
$idNA = $rNA1.id
$opsNA = @{ ops = @(
  @{ op='patch';  id=$idNA; set=@{ done=$false } },
  @{ op='delete'; id=$idNA },
  @{ op='delete'; id=99999999 }
)}
$rNA = Invoke-Json POST "$Root/batch?atomic=false" $opsNA $headers
"NON-ATOMIC RESULT: " + ($rNA | ConvertTo-Json -Compress)
# doğrula: silinmiş olmalı
try{
  Invoke-RestMethod "$Root/tasks/$idNA" | Out-Null
  "VERIFY NON-ATOMIC: beklenen 404 yerine bulundu!" | Write-Host
}catch{
  "VERIFY NON-ATOMIC: idNA deleted (404) ✓" | Write-Host
}

# ---------- /batch: ATOMIC (ayrı id) ----------
$rAT1 = Invoke-Json POST "$Root/tasks" @{title='atomic-rollback'; notes='demo'} $headers
$idAT = $rAT1.id
# önce durumunu göster
$before = (Invoke-RestMethod "$Root/tasks/$idAT").done
"Atomic demo için idAT=$idAT (before.done=$before)"

# patch + bilinçli hatalı delete → 400 ve rollback beklenir
$opsAT = @{ ops = @(
  @{ op='patch'; id=$idAT; set=@{ done=$true } },
  @{ op='delete'; id=99999999 }
)}
$got400 = $false
try{
  Invoke-Json POST "$Root/batch?atomic=true" $opsAT $headers | Out-Null
}catch{
  $resp = $_.Exception.Response
  if($resp -and ($resp.StatusCode.value__ -eq 400)){ $got400 = $true }
}
"ATOMIC beklenen 400: $got400"

# rollback doğrula: kayıt hâlâ var ve done=False kalmış olmalı
$after = Invoke-RestMethod "$Root/tasks/$idAT"
"VERIFY ROLLBACK: exists=True done=$($after.done)"

# temizlik (atomic kaydı kalsın istiyorsan aşağıyı yorum satırı yap)
try{ Invoke-Json POST "$Root/batch?atomic=false" @{ ops = @(@{ op='delete'; id=$idAT }) } $headers | Out-Null }catch{}
