param(
  [string]$Dir="C:\maiq_demo\apps\todo_api\backups",
  [int]$KeepDays=30
)
if(Test-Path $Dir){
  Get-ChildItem $Dir -File | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } | Remove-Item -Force
}
