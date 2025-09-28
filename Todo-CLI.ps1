param(
  [string]$Root = "http://127.0.0.1:9103"
)

function Invoke-TodoApi {
  param(
    [Parameter(Mandatory=$true)][ValidateSet('GET','POST','PATCH')][string]$Method,
    [Parameter(Mandatory=$true)][string]$Path,
    [Hashtable]$Body
  )
  $url = "$Root$Path"
  if ($Body) {
    $json  = $Body | ConvertTo-Json -Compress -Depth 10
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    return Invoke-RestMethod -Method $Method -Uri $url -ContentType 'application/json; charset=utf-8' -Body $bytes
  } else {
    return Invoke-RestMethod -Method $Method -Uri $url
  }
}

function Health-Todo { Invoke-RestMethod "$Root/health" }

function Metrics-Todo { Invoke-RestMethod "$Root/metrics" }

function Add-Todo {
  param(
    [Parameter(Mandatory=$true)][string]$Title,
    [string]$Description,
    [string[]]$Tags
  )
  $b = @{ title = $Title }
  if ($PSBoundParameters.ContainsKey('Description') -and $Description) { $b.description = $Description }
  if ($PSBoundParameters.ContainsKey('Tags') -and $Tags) { $b.tags = $Tags }
  $t = Invoke-TodoApi -Method POST -Path '/tasks' -Body $b
  "OK: id=$($t.id) '$($t.title)' eklendi."
}

function Done-Todo {
  param([Parameter(Mandatory=$true)][int]$Id)
  Invoke-TodoApi -Method PATCH -Path "/tasks/$Id" -Body @{ done = $true } | Out-Null
  "OK: id=$Id done=true"
}

function List-Todo {
  param([switch]$Done,[int]$Limit=20,[int]$Offset=0)
  $q = if ($Done) { "done=true&limit=$Limit&offset=$Offset" } else { "limit=$Limit&offset=$Offset" }
  Invoke-RestMethod "$Root/tasks?$q"
}
function Done-TodoByTitle {
  param([Parameter(Mandatory=$true)][string]$Title)
  $root = "http://127.0.0.1:9103"
  $items = Invoke-RestMethod "$root/tasks?limit=200&offset=0"
  $match = $items | Where-Object { $_.title -like "*$Title*" } | Sort-Object id -Descending | Select-Object -First 1
  if (-not $match) { throw "Eşleşen görev bulunamadı." }
  Invoke-RestMethod -Method Patch "$root/tasks/$($match.id)" -ContentType 'application/json' -Body (@{done=$true}|ConvertTo-Json) | Out-Null
  "OK: id=$($match.id) '$($match.title)' done=true"
}

function Done-LastTodo {
  $root = "http://127.0.0.1:9103"
  $items = Invoke-RestMethod "$root/tasks?limit=1&offset=0"
  if (-not $items -or -not $items[0]) { throw "Hiç görev yok." }
  $last = $items | Sort-Object id -Descending | Select-Object -First 1
  Invoke-RestMethod -Method Patch "$root/tasks/$($last.id)" -ContentType 'application/json' -Body (@{done=$true}|ConvertTo-Json) | Out-Null
  "OK: id=$($last.id) '$($last.title)' done=true"
}
function Done-TodoByTitle {
  param([Parameter(Mandatory=$true)][string]$Title)
  $root = "http://127.0.0.1:9103"
  $items = Invoke-RestMethod "$root/tasks?limit=200&offset=0"

  # Basit ve sağlam: özel harf sorunlarından etkilenmemek için kısmi arama
  # Örn: -Title "Toplant" yazmak yeterli.
  $match = $items | Where-Object { $_.title -like "*$Title*" } |
           Sort-Object id -Descending | Select-Object -First 1

  if (-not $match) { throw "Eşleşen görev bulunamadı. (İpucu: 'Toplantı' yerine 'Toplant' deneyin)" }

  Invoke-RestMethod -Method Patch "$root/tasks/$($match.id)" `
    -ContentType 'application/json' `
    -Body (@{done=$true} | ConvertTo-Json) | Out-Null

  "OK: id=$($match.id) '$($match.title)' done=true"
}
