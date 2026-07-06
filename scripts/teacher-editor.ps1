$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ApiHost = "127.0.0.1"
$ApiPort = 8000
$WebHost = "127.0.0.1"
$WebPort = 5173
$EditorUrl = "http://$WebHost`:$WebPort/admin/content"
$ApiDir = Join-Path $Root "apps\api"
$WebDir = Join-Path $Root "apps\web"
$Requirements = Join-Path $ApiDir "requirements.txt"
$VenvDir = Join-Path $Root ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$LogDir = Join-Path $Root ".teacher-editor-logs"
$ApiOutLog = Join-Path $LogDir "api.out.log"
$ApiErrLog = Join-Path $LogDir "api.err.log"
$WebOutLog = Join-Path $LogDir "web.out.log"
$WebErrLog = Join-Path $LogDir "web.err.log"

$MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$env:Path = @($env:Path, $MachinePath, $UserPath) -join ";"

function Write-Step {
  param([string] $Message)
  Write-Host ""
  Write-Host "== $Message ==" -ForegroundColor Cyan
}

function Test-Command {
  param([string] $Name)
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-Checked {
  param(
    [string] $Title,
    [string] $FilePath,
    [string[]] $Arguments,
    [string] $WorkingDirectory = $Root
  )

  Write-Host $Title
  Push-Location $WorkingDirectory
  try {
    & $FilePath @Arguments
    $exitCode = $LASTEXITCODE
  } finally {
    Pop-Location
  }

  if ($exitCode -ne 0) {
    throw "$Title failed with exit code $exitCode."
  }
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

function Wait-LocalPort {
  param(
    [string] $Name,
    [string] $HostName,
    [int] $Port,
    [System.Diagnostics.Process] $Process,
    [string] $ErrorLog
  )

  for ($i = 0; $i -lt 80; $i += 1) {
    if (Test-LocalPort $HostName $Port) {
      Write-Host "$Name is ready on http://$HostName`:$Port" -ForegroundColor Green
      return
    }

    if ($Process -and $Process.HasExited) {
      Write-Host "$Name process exited early. Error log:" -ForegroundColor Red
      if (Test-Path $ErrorLog) {
        Get-Content $ErrorLog -Tail 60
      }
      throw "$Name failed to start."
    }

    Start-Sleep -Milliseconds 500
  }

  Write-Host "$Name did not become ready in time. Error log:" -ForegroundColor Red
  if (Test-Path $ErrorLog) {
    Get-Content $ErrorLog -Tail 60
  }
  throw "$Name did not become ready on http://$HostName`:$Port."
}

function Ensure-PythonEnvironment {
  if (Test-Path $PythonExe) {
    Write-Host "Python virtualenv found: $PythonExe"
    return
  }

  Write-Step "Preparing Python virtualenv"

  if (Test-Command "py") {
    Invoke-Checked "Creating .venv with py -3" "py" @("-3", "-m", "venv", $VenvDir)
  } elseif (Test-Command "python") {
    Invoke-Checked "Creating .venv with python" "python" @("-m", "venv", $VenvDir)
  } else {
    throw "Python was not found. Please install Python 3 and run this launcher again."
  }

  if (-not (Test-Path $PythonExe)) {
    throw "Virtualenv was created, but $PythonExe was not found."
  }
}

function Ensure-ApiDependencies {
  if (-not (Test-Path $Requirements)) {
    throw "API requirements file was not found: $Requirements"
  }

  Write-Step "Installing API dependencies"
  Invoke-Checked "Upgrading pip" $PythonExe @("-m", "pip", "install", "--upgrade", "pip")
  Invoke-Checked "Installing apps\api requirements" $PythonExe @("-m", "pip", "install", "-r", $Requirements)
}

function Ensure-WebDependencies {
  if (-not (Test-Path (Join-Path $WebDir "package.json"))) {
    throw "Web package.json was not found: $WebDir"
  }

  if (-not (Test-Command "npm")) {
    throw "npm was not found. Please install Node.js LTS and run this launcher again."
  }

  $viteBin = Join-Path $WebDir "node_modules\.bin\vite.cmd"
  if (Test-Path $viteBin) {
    Write-Host "Web dependencies found: apps\web\node_modules"
    return
  }

  Write-Step "Installing web dependencies"
  Invoke-Checked "Running npm install in apps\web" "npm" @("install") $WebDir
}

function Start-Api {
  if (Test-LocalPort $ApiHost $ApiPort) {
    Write-Host "API is already available on http://$ApiHost`:$ApiPort" -ForegroundColor Green
    return $null
  }

  Write-Step "Starting API"
  $process = Start-Process -FilePath $PythonExe `
    -ArgumentList @("-m", "uvicorn", "apps.api.main:app", "--host", $ApiHost, "--port", "$ApiPort") `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $ApiOutLog `
    -RedirectStandardError $ApiErrLog `
    -PassThru
  Write-Host "API process started: $($process.Id)"
  return $process
}

function Start-Web {
  if (Test-LocalPort $WebHost $WebPort) {
    Write-Host "Web app is already available on http://$WebHost`:$WebPort" -ForegroundColor Green
    return $null
  }

  Write-Step "Starting web editor"
  $process = Start-Process -FilePath "cmd.exe" `
    -ArgumentList @("/c", "npm run dev -- --host $WebHost --port $WebPort") `
    -WorkingDirectory $WebDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $WebOutLog `
    -RedirectStandardError $WebErrLog `
    -PassThru
  Write-Host "Web process started: $($process.Id)"
  return $process
}

try {
  New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

  Write-Host "Chronovita teacher editor launcher"
  Write-Host "Project root: $Root"

  Ensure-PythonEnvironment
  Ensure-ApiDependencies
  Ensure-WebDependencies

  $apiProcess = Start-Api
  $webProcess = Start-Web

  Wait-LocalPort "API" $ApiHost $ApiPort $apiProcess $ApiErrLog
  Wait-LocalPort "Web editor" $WebHost $WebPort $webProcess $WebErrLog

  Write-Step "Opening editor"
  Write-Host $EditorUrl -ForegroundColor Green
  Start-Process $EditorUrl
  Write-Host ""
  Write-Host "Ready. Keep this window open if you want to read the launch log."
  Write-Host "Runtime logs are saved in: $LogDir"
} catch {
  Write-Host ""
  Write-Host "Launch failed:" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  Write-Host ""
  Write-Host "Please send the logs in this folder to the developer team:"
  Write-Host $LogDir
  exit 1
}
