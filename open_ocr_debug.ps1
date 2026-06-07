$p = Join-Path $env:APPDATA 'WARFRAME-RELIC\ocr_debug'
if (!(Test-Path $p)) { New-Item -ItemType Directory -Path $p -Force | Out-Null }
Write-Output "DIR: $p"
Get-ChildItem $p
Start-Process explorer.exe $p
