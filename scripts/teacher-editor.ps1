$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ApiHost = "127.0.0.1"
$ApiPort = 8000
$WebHost = "127.0.0.1"
$WebPort = 5173
$EditorUrl = "http://$WebHost`:$WebPort/admin/content"
$WebDir = Join-Path $Root "apps\web"
$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
  $PythonExe = "python"
  Write-Warning "Python virtualenv was not found at .venv. Falling back to python on PATH."
}

if (-not (Test-Path (Join-Path $WebDir "node_modules"))) {
  Write-Warning "apps\web\node_modules was not found. Run npm install inside apps\web before first use."
}

function Test-LocalPort {
  param(
    [string] $HostName,
    [int] $Port
  )

  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $async = $client.BeginConnect($HostName, $Port, $null, $null)
    if (-not $async.AsyncWaitHandle.WaitOne(350)) {
      return $false
    }
    $client.EndConnect($async)
    return $true
  } catch {
    return $false
  } finally {
    $client.Close()
  }
}

function Start-HiddenPowerShell {
  param([string] $Command)

  Start-Process -FilePath "powershell" -WindowStyle Hidden -PassThru -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    $Command
  )
}

Write-Host "Starting Chronovita teacher editor..."

if (Test-LocalPort $ApiHost $ApiPort) {
  Write-Host "API is already available on http://$ApiHost`:$ApiPort"
} else {
  $apiCommand = "Set-Location -LiteralPath '$Root'; & '$PythonExe' -m uvicorn apps.api.main:app --host $ApiHost --port $ApiPort"
  $apiProcess = Start-HiddenPowerShell $apiCommand
  Write-Host "API process started: $($apiProcess.Id)"
}

if (Test-LocalPort $WebHost $WebPort) {
  Write-Host "Web app is already available on http://$WebHost`:$WebPort"
} else {
  $webCommand = "Set-Location -LiteralPath '$WebDir'; npm run dev -- --host $WebHost --port $WebPort"
  $webProcess = Start-HiddenPowerShell $webCommand
  Write-Host "Web process started: $($webProcess.Id)"
}

for ($i = 0; $i -lt 40; $i += 1) {
  if (Test-LocalPort $WebHost $WebPort) {
    break
  }
  Start-Sleep -Milliseconds 500
}

Write-Host "Opening $EditorUrl"
Start-Process $EditorUrl
Write-Host "Done. Keep this window if you want the launch log."
