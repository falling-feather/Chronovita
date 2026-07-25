$ErrorActionPreference = "Stop"

$ApiUrl = "http://127.0.0.1:8000/healthz"
$EditorUrl = "http://127.0.0.1:5173/admin/content"
$Ports = @(8000, 5173)

try {
  $connections = @(
    $Ports |
      ForEach-Object {
        Get-NetTCPConnection `
          -State Listen `
          -LocalPort $_ `
          -ErrorAction SilentlyContinue
      }
  )
  if ($connections.Count -eq 0) {
    Write-Host "Chronovita teacher editor is not running." -ForegroundColor Green
    return
  }

  if (@($connections.LocalPort | Sort-Object -Unique).Count -ne 2) {
    throw "Only one editor port is active. Refusing to stop an unknown partial service."
  }
  $health = Invoke-RestMethod -Method Get -Uri $ApiUrl -TimeoutSec 3
  $editor = Invoke-WebRequest `
    -UseBasicParsing `
    -Method Get `
    -Uri $EditorUrl `
    -TimeoutSec 3
  if (
    $health.status -ne "alive" `
    -or $editor.StatusCode -ne 200 `
    -or $editor.Content -notmatch "Chronovita"
  ) {
    throw "The active ports do not belong to a healthy Chronovita editor."
  }

  $processIds = @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
  foreach ($processId in $processIds) {
    if ($processId -gt 0) {
      & taskkill.exe /PID "$processId" /T /F 2>$null | Out-Null
    }
  }
  Start-Sleep -Seconds 1
  $remaining = @(
    $Ports |
      ForEach-Object {
        Get-NetTCPConnection `
          -State Listen `
          -LocalPort $_ `
          -ErrorAction SilentlyContinue
      }
  )
  if ($remaining.Count -ne 0) {
    throw "Chronovita editor ports are still active."
  }
  Write-Host "Chronovita teacher editor stopped." -ForegroundColor Green
} catch {
  Write-Host ""
  Write-Host "Stop failed:" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  throw
}
