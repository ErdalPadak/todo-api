param([string]$Root="http://127.0.0.1:9103",[string]$Svc="todo-api-9103")
try{
  $r = Invoke-WebRequest "$Root/health" -UseBasicParsing -TimeoutSec 5
  if($r.StatusCode -ne 200 -or $r.Content -notmatch '"healthy"'){ throw "bad health" }
}catch{
  nssm restart $Svc | Out-Null
}
