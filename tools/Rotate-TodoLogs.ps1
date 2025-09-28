param(
  [string]$Svc="todo-api-9103",
  [string]$LogDir="C:\maiq_demo\apps\todo_api\logs",
  [int]$KeepDays=14
)
$dt=(Get-Date -Format 'yyyyMMdd-HHmmss')
$outs=@("$LogDir\todo-api.out.log","$LogDir\todo-api.err.log")
nssm stop $Svc | Out-Null
foreach($p in $outs){
  if(Test-Path $p -and (Get-Item $p).Length -gt 0){
    $target="$($p).$dt"
    Move-Item $p $target -Force
    Compress-Archive -Path $target -DestinationPath "$target.zip" -Force
    Remove-Item $target -Force
  }
}
Get-ChildItem $LogDir -Filter *.zip | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } | Remove-Item -Force
nssm start $Svc | Out-Null
