param()

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeState = Join-Path $Root ".chronovita-review\runtime.json"

if (-not (Test-Path -LiteralPath $RuntimeState -PathType Leaf)) {
  Write-Host "No Chronovita review runtime is recorded."
  exit 0
}

$runtime = Get-Content -LiteralPath $RuntimeState -Raw | ConvertFrom-Json
$candidateIds = New-Object System.Collections.Generic.HashSet[int]
foreach ($property in @("web_pid", "api_pid")) {
  $value = [int] $runtime.$property
  if ($value -gt 0 -and $value -ne $PID) {
    [void] $candidateIds.Add($value)
  }
}

$getConnections = Get-Command "Get-NetTCPConnection" -ErrorAction SilentlyContinue
if ($getConnections) {
  foreach ($port in @([int] $runtime.web_port, [int] $runtime.api_port)) {
    $owners = @(
      Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    )
    foreach ($ownerId in $owners) {
      if ($ownerId -gt 0 -and $ownerId -ne $PID) {
        [void] $candidateIds.Add([int] $ownerId)
      }
    }
  }
}

foreach ($processId in $candidateIds) {
  Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}

Remove-Item -LiteralPath $RuntimeState -Force
Write-Host "Chronovita review services stopped."
