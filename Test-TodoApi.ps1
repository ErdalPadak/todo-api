param([string]$Root = "http://127.0.0.1:9103")

$r = Invoke-RestMethod "$Root/health"
if ($r.status -ne "healthy") { throw "/health beklenen 'healthy' değildi." }
"health OK"

$task = Invoke-RestMethod -Method Post "$Root/tasks" -ContentType 'application/json' -Body (@{title="pytest"} | ConvertTo-Json)
if (-not $task.id) { throw "/tasks dönüşünde id yok." }
$tid = $task.id
"created id=$tid"

$null = Invoke-RestMethod -Method Patch "$Root/tasks/$tid" -ContentType 'application/json' -Body (@{done=$true} | ConvertTo-Json)
"patched done=true"

$m = Invoke-RestMethod "$Root/metrics"
foreach ($k in @("count","done","open")) {
  if (-not $m.PSObject.Properties.Name.Contains($k)) { throw "/metrics içinde '$k' alanı yok." }
}
"metrics OK -> " + ($m | ConvertTo-Json -Compress)
"ALL GOOD ✅"
