param(
  [switch] $Lan,
  [ValidateRange(1024, 65535)]
  [int] $Port = 8000,
  [switch] $SkipBrowser,
  [switch] $SkipDependencyInstall
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Requirements = Join-Path $Root "apps\api\requirements.lock"
$WebDist = Join-Path $Root "apps\web\dist"
$Wheelhouse = Join-Path $Root "distribution\wheelhouse\windows-py311"
$ModelRoot = Join-Path $Root "distribution\models\BAAI-bge-small-zh-v1.5"
$VenvDir = Join-Path $Root ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$DependencyStamp = Join-Path $VenvDir ".chronovita-classroom-requirements.sha256"
$RuntimeDir = Join-Path $Root ".chronovita-classroom"
$LogDir = Join-Path $RuntimeDir "logs"
$RuntimeState = Join-Path $RuntimeDir "runtime.json"
$ApiOutLog = Join-Path $LogDir "classroom.out.log"
$ApiErrLog = Join-Path $LogDir "classroom.err.log"
$DatabasePath = Join-Path $Root "data\classroom\chronovita.db"
$RagIndexPath = Join-Path $Root "data\classroom\rag-index-v1.sqlite3"
$BindHost = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
$LocalUrl = "http://127.0.0.1`:$Port"

function Write-Step {
  param([string] $Message)
  Write-Host ""
  Write-Host "== $Message ==" -ForegroundColor Cyan
}

function Quote-ProcessArgument {
  param([string] $Value)
  if ($Value -notmatch '[\s"]') {
    return $Value
  }
  return '"' + ($Value -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"'
}

function Invoke-Checked {
  param(
    [string] $Label,
    [string] $FilePath,
    [string[]] $Arguments
  )
  & $FilePath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with exit code $LASTEXITCODE."
  }
}

function Test-Python311 {
  param(
    [string] $FilePath,
    [string[]] $PrefixArguments = @()
  )
  $previous = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    & $FilePath @PrefixArguments -c `
      "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" `
      *> $null
    return $LASTEXITCODE -eq 0
  } finally {
    $ErrorActionPreference = $previous
  }
}

function Get-Python311 {
  $python = Get-Command "python.exe" -ErrorAction SilentlyContinue
  if ($python -and (Test-Python311 $python.Source)) {
    return [PSCustomObject]@{
      FilePath = $python.Source
      PrefixArguments = @()
      Label = "python"
    }
  }
  $py = Get-Command "py.exe" -ErrorAction SilentlyContinue
  if ($py -and (Test-Python311 $py.Source @("-3.11"))) {
    return [PSCustomObject]@{
      FilePath = $py.Source
      PrefixArguments = @("-3.11")
      Label = "py -3.11"
    }
  }
  throw "Python 3.11 was not found. Install Python 3.11 and run the classroom launcher again."
}

function Ensure-PythonEnvironment {
  if (Test-Path -LiteralPath $PythonExe -PathType Leaf) {
    if (-not (Test-Python311 $PythonExe)) {
      throw "The existing .venv is not Python 3.11. Move it aside and launch again."
    }
    return
  }
  Write-Step "Preparing Python 3.11 virtual environment"
  $runtime = Get-Python311
  $arguments = @($runtime.PrefixArguments) + @(
    "-m",
    "venv",
    (Quote-ProcessArgument $VenvDir)
  )
  Invoke-Checked "Creating .venv with $($runtime.Label)" $runtime.FilePath $arguments
  if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python virtual environment was not created correctly."
  }
}

function Get-DependencyFingerprint {
  return (Get-FileHash -LiteralPath $Requirements -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Test-DependenciesCurrent {
  if (-not (Test-Path -LiteralPath $DependencyStamp -PathType Leaf)) {
    return $false
  }
  if ((Get-Content -LiteralPath $DependencyStamp -Raw).Trim() -ne (Get-DependencyFingerprint)) {
    return $false
  }
  & $PythonExe -c "import fastapi, fastembed, pydantic_settings, sqlalchemy, uvicorn" *> $null
  return $LASTEXITCODE -eq 0
}

function Ensure-ApiDependencies {
  if (-not (Test-Path -LiteralPath $Requirements -PathType Leaf)) {
    throw "API dependency lock file is missing: $Requirements"
  }
  if (Test-DependenciesCurrent) {
    Write-Host "Python dependencies are current; reusing .venv."
    return
  }
  if ($SkipDependencyInstall) {
    throw "Dependencies are not installed and -SkipDependencyInstall was requested."
  }
  Write-Step "Installing hash-locked classroom dependencies"
  $arguments = @(
    "-m",
    "pip",
    "install",
    "--disable-pip-version-check",
    "--require-hashes",
    "-r",
    (Quote-ProcessArgument $Requirements)
  )
  $wheels = @(
    Get-ChildItem -LiteralPath $Wheelhouse -File -ErrorAction SilentlyContinue
  )
  if ($wheels.Count -gt 0) {
    $arguments = @(
      "-m",
      "pip",
      "install",
      "--disable-pip-version-check",
      "--no-index",
      "--find-links",
      (Quote-ProcessArgument $Wheelhouse),
      "--require-hashes",
      "-r",
      (Quote-ProcessArgument $Requirements)
    )
    Write-Host "Using bundled Windows wheelhouse; no network is required."
  } else {
    Write-Warning "Bundled wheelhouse is absent; this source launch may need internet access."
  }
  Invoke-Checked "Installing classroom dependencies" $PythonExe $arguments
  Set-Content -LiteralPath $DependencyStamp -Value (Get-DependencyFingerprint) -Encoding ASCII
}

function Assert-PrebuiltWeb {
  if (
    -not (Test-Path -LiteralPath (Join-Path $WebDist "index.html") -PathType Leaf) `
    -or -not (Test-Path -LiteralPath (Join-Path $WebDist "assets") -PathType Container)
  ) {
    throw "Prebuilt classroom web app is missing. Use the official classroom package or run npm build."
  }
}

function Test-LocalPort {
  param([int] $TargetPort)
  $client = New-Object Net.Sockets.TcpClient
  try {
    $task = $client.ConnectAsync("127.0.0.1", $TargetPort)
    return $task.Wait(350) -and $client.Connected
  } catch {
    return $false
  } finally {
    $client.Dispose()
  }
}

function Get-LanAddresses {
  $addresses = @()
  try {
    $addresses = @(
      Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object {
          $_.IPAddress -ne "127.0.0.1" `
            -and $_.IPAddress -notlike "169.254.*" `
            -and $_.AddressState -eq "Preferred"
        } |
        Select-Object -ExpandProperty IPAddress -Unique
    )
  } catch {
    $addresses = @(
      [Net.Dns]::GetHostAddresses([Net.Dns]::GetHostName()) |
        Where-Object {
          $_.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork `
            -and $_.ToString() -ne "127.0.0.1" `
            -and $_.ToString() -notlike "169.254.*"
        } |
        ForEach-Object { $_.ToString() }
    )
  }
  return @($addresses | Sort-Object -Unique)
}

function Set-ClassroomEnvironment {
  param([string[]] $LanAddresses)

  $preserveNames = @(
    "CHRONO_LLM_PROVIDER",
    "CHRONO_DEEPSEEK_API_KEY",
    "CHRONO_DEEPSEEK_BASE_URL",
    "CHRONO_DEEPSEEK_ALLOWED_HOSTS",
    "CHRONO_DEEPSEEK_MODEL",
    "CHRONO_DEEPSEEK_MODEL_PRO",
    "CHRONO_DEEPSEEK_THINKING",
    "CHRONO_CLASSROOM_ADMIN_PASSWORD"
  )
  $preserved = @{}
  foreach ($name in $preserveNames) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if (-not [string]::IsNullOrWhiteSpace($value)) {
      $preserved[$name] = $value
    }
  }
  foreach ($key in @([Environment]::GetEnvironmentVariables().Keys)) {
    $name = $key.ToString()
    if ($name.StartsWith("CHRONO_", [StringComparison]::OrdinalIgnoreCase)) {
      [Environment]::SetEnvironmentVariable($name, $null)
    }
  }
  foreach ($entry in $preserved.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value)
  }

  $cleanLanAddresses = @(
    $LanAddresses |
      Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
  )
  $trustedHosts = @("127.0.0.1", "localhost") + $cleanLanAddresses
  $origins = @("http://127.0.0.1`:$Port", "http://localhost`:$Port")
  if ($Lan) {
    $origins += @($cleanLanAddresses | ForEach-Object { "http://$_`:$Port" })
  }
  $env:CHRONO_DISABLE_DOTENV = "true"
  $env:CHRONO_RUNTIME_PROFILE = "local"
  $env:CHRONO_API_WORKER_COUNT = "1"
  $env:CHRONO_DEBUG = "false"
  $env:CHRONO_CORS_ORIGINS = ConvertTo-Json -InputObject @($origins) -Compress
  $env:CHRONO_TRUSTED_HOSTS = ConvertTo-Json -InputObject @($trustedHosts) -Compress
  $env:CHRONO_SQLITE_PATH = $DatabasePath
  $env:CHRONO_DATABASE_MIGRATION_MODE = "apply-safe"
  $env:CHRONO_CONTENT_ROOT = (Join-Path $Root "content")
  $env:CHRONO_SERVE_WEB_APP = "true"
  $env:CHRONO_WEB_DIST_ROOT = $WebDist
  $env:CHRONO_AUTH_MODE = "accounts"
  $env:CHRONO_AUTH_COOKIE_SECURE = "false"
  $env:CHRONO_AUTH_BOOTSTRAP_USERNAME = ""
  $env:CHRONO_AUTH_BOOTSTRAP_PASSWORD = ""
  $env:CHRONO_ADMIN_TOKEN = ""
  $env:CHRONO_GITHUB_PUBLICATION_ENABLED = "false"
  $env:CHRONO_GITHUB_PUBLICATION_TOKEN = ""
  $env:CHRONO_RAG_INDEX_PATH = $RagIndexPath
  $env:CHRONO_RAG_MODEL_ROOT = $ModelRoot
  $env:CHRONO_RAG_VECTOR_ENABLED = "true"
  if ([string]::IsNullOrWhiteSpace($env:CHRONO_LLM_PROVIDER)) {
    $env:CHRONO_LLM_PROVIDER = "mock"
  }
}

function Initialize-ClassroomDatabase {
  Write-Step "Checking classroom administrator"
  & $PythonExe (Join-Path $Root "scripts\initialize_classroom.py") `
    --database $DatabasePath `
    --username admin `
    --display-name "Chronovita Classroom Admin"
  $exitCode = $LASTEXITCODE
  $env:CHRONO_CLASSROOM_ADMIN_PASSWORD = $null
  if ($exitCode -ne 0) {
    throw "Classroom administrator initialization failed."
  }
}

function Test-ExistingClassroom {
  if (-not (Test-LocalPort $Port)) {
    return $false
  }
  try {
    $health = Invoke-RestMethod -Method Get -Uri "$LocalUrl/healthz" -TimeoutSec 3
    $page = Invoke-WebRequest -UseBasicParsing -Method Get -Uri "$LocalUrl/login" -TimeoutSec 3
    return $health.status -eq "alive" -and $page.Content -match "Chronovita"
  } catch {
    return $false
  }
}

function Wait-ClassroomReady {
  param([Diagnostics.Process] $Process)
  for ($attempt = 0; $attempt -lt 120; $attempt++) {
    if ($Process.HasExited) {
      $tail = ""
      if (Test-Path -LiteralPath $ApiErrLog -PathType Leaf) {
        $tail = (Get-Content -LiteralPath $ApiErrLog -Tail 20) -join [Environment]::NewLine
      }
      throw "Classroom service exited before readiness.`n$tail"
    }
    try {
      $ready = Invoke-RestMethod -Method Get -Uri "$LocalUrl/readyz" -TimeoutSec 2
      $page = Invoke-WebRequest -UseBasicParsing -Method Get -Uri "$LocalUrl/login" -TimeoutSec 2
      if ($ready.status -eq "ready" -and $page.Content -match "Chronovita") {
        return
      }
    } catch {
      # Readiness can fail either by throwing or by returning a non-ready state.
    }
    Start-Sleep -Milliseconds 500
  }
  throw "Chronovita classroom did not become ready. Review $ApiErrLog."
}

function Get-ClassroomServicePid {
  param([Diagnostics.Process] $LauncherProcess)
  $owners = @(
    Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop |
      Select-Object -ExpandProperty OwningProcess -Unique
  )
  if ($owners.Count -ne 1) {
    throw "Expected one classroom listener process on port $Port."
  }
  $servicePid = [int]$owners[0]
  if ($servicePid -eq $LauncherProcess.Id) {
    return $servicePid
  }

  $cursor = $servicePid
  for ($depth = 0; $depth -lt 8; $depth++) {
    $process = Get-CimInstance Win32_Process `
      -Filter "ProcessId = $cursor" `
      -ErrorAction Stop
    if ($null -eq $process) {
      break
    }
    $parent = [int]$process.ParentProcessId
    if ($parent -eq $LauncherProcess.Id) {
      return $servicePid
    }
    if ($parent -le 0 -or $parent -eq $cursor) {
      break
    }
    $cursor = $parent
  }
  throw "Classroom port owner is not part of the launched Python process tree."
}

function Stop-ProcessTree {
  param([Diagnostics.Process] $Process)
  if (-not $Process -or $Process.HasExited) {
    return
  }
  try {
    & taskkill.exe /PID "$($Process.Id)" /T /F 2>$null | Out-Null
  } catch {
    Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
  }
}

if ($MyInvocation.InvocationName -eq ".") {
  return
}

$classroomProcess = $null
try {
  New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
  Write-Host "Chronovita classroom launcher"
  Write-Host "Package root: $Root"
  Write-Host "Mode: $(if ($Lan) { 'LAN classroom (explicit)' } else { 'local loopback (default)' })"

  if (Test-LocalPort $Port) {
    if (Test-ExistingClassroom) {
      Write-Host "Chronovita classroom is already running at $LocalUrl" -ForegroundColor Green
      if (-not $SkipBrowser) { Start-Process $LocalUrl }
      exit 0
    }
    throw "Port $Port is already used by another service."
  }

  Ensure-PythonEnvironment
  Ensure-ApiDependencies
  Assert-PrebuiltWeb

  $lanAddresses = if ($Lan) { Get-LanAddresses } else { @() }
  if ($Lan -and $lanAddresses.Count -eq 0) {
    throw "LAN mode was requested, but no usable IPv4 classroom address was found."
  }
  Set-ClassroomEnvironment -LanAddresses $lanAddresses

  & $PythonExe (Join-Path $Root "scripts\prepare_rag_model.py") `
    --verify-only --target $ModelRoot *> $null
  if ($LASTEXITCODE -ne 0) {
    $env:CHRONO_RAG_VECTOR_ENABLED = "false"
    Write-Warning "The local vector model is unavailable; classroom RAG will use FTS5 only."
  }

  Initialize-ClassroomDatabase

  Write-Step "Starting single-port classroom service"
  $classroomProcess = Start-Process -FilePath $PythonExe `
    -ArgumentList @(
      "-m",
      "uvicorn",
      "apps.api.main:app",
      "--host",
      $BindHost,
      "--port",
      "$Port",
      "--workers",
      "1"
    ) `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $ApiOutLog `
    -RedirectStandardError $ApiErrLog `
    -PassThru
  $env:CHRONO_DEEPSEEK_API_KEY = $null
  Wait-ClassroomReady -Process $classroomProcess
  $servicePid = Get-ClassroomServicePid -LauncherProcess $classroomProcess

  [PSCustomObject]@{
    schema_version = "chronovita-classroom-runtime/v1"
    pid = $servicePid
    launcher_pid = $classroomProcess.Id
    port = $Port
    bind_host = $BindHost
    lan = [bool]$Lan
    started_at = [DateTime]::UtcNow.ToString("o")
  } | ConvertTo-Json | Set-Content -LiteralPath $RuntimeState -Encoding UTF8

  Write-Step "Classroom ready"
  Write-Host "Teacher link: $LocalUrl" -ForegroundColor Green
  if ($Lan) {
    Write-Host "Student links:" -ForegroundColor Cyan
    foreach ($address in $lanAddresses) {
      Write-Host "  http://$address`:$Port" -ForegroundColor Green
    }
    Write-Host "Only this explicit -Lan launch listens beyond the local computer."
  } else {
    Write-Host "This default launch is available only on this computer."
  }
  if (-not $SkipBrowser) {
    Start-Process $LocalUrl
  }
} catch {
  Stop-ProcessTree -Process $classroomProcess
  Write-Host ""
  Write-Host "Classroom launch failed:" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  throw
}
