param(
  [ValidateRange(1024, 65535)]
  [int] $Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeDir = Join-Path $Root ".chronovita-classroom"
$RuntimeState = Join-Path $RuntimeDir "runtime.json"
$LocalUrl = "http://127.0.0.1`:$Port"

try {
  $connections = @(
    Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
  )
  if ($connections.Count -eq 0) {
    Write-Host "Chronovita classroom is not running." -ForegroundColor Green
    return
  }
  if (-not (Test-Path -LiteralPath $RuntimeState -PathType Leaf)) {
    throw "Runtime ownership record is missing; refusing to stop an unknown service on port $Port."
  }
  $state = Get-Content -LiteralPath $RuntimeState -Raw | ConvertFrom-Json
  if (
    $state.schema_version -ne "chronovita-classroom-runtime/v1" `
    -or [int]$state.port -ne $Port `
    -or [int]$state.pid -le 0
  ) {
    throw "Runtime ownership record is invalid."
  }
  $owners = @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
  if ($owners.Count -ne 1 -or [int]$owners[0] -ne [int]$state.pid) {
    throw "Port owner does not match the recorded classroom process; refusing to stop it."
  }
  $health = Invoke-RestMethod -Method Get -Uri "$LocalUrl/healthz" -TimeoutSec 3
  $page = Invoke-WebRequest -UseBasicParsing -Method Get -Uri "$LocalUrl/login" -TimeoutSec 3
  if ($health.status -ne "alive" -or $page.Content -notmatch "Chronovita") {
    throw "The recorded process is not a healthy Chronovita classroom service."
  }

  & taskkill.exe /PID "$($state.pid)" /T /F 2>$null | Out-Null
  Start-Sleep -Seconds 1
  if (@(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue).Count -ne 0) {
    throw "Classroom port $Port is still active."
  }
  Remove-Item -LiteralPath $RuntimeState -Force -ErrorAction SilentlyContinue
  Write-Host "Chronovita classroom stopped. Local accounts and learning data were preserved." -ForegroundColor Green
} catch {
  Write-Host ""
  Write-Host "Stop failed:" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  throw
}
