param([switch] $SkipBrowser)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ApiHost = "127.0.0.1"
$ApiPort = 8000
$WebHost = "127.0.0.1"
$WebPort = 5173
$EditorUrl = "http://$WebHost`:$WebPort/admin/content"
$ApiDir = Join-Path $Root "apps\api"
$WebDir = Join-Path $Root "apps\web"
$Requirements = Join-Path $ApiDir "requirements.lock"
$VersionFile = Join-Path $Root "services\version.py"
$VenvDir = Join-Path $Root ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$ApiDepsStamp = Join-Path $VenvDir ".chronovita-api-requirements.sha256"
$LogDir = Join-Path $Root ".teacher-editor-logs"
$ApiOutLog = Join-Path $LogDir "api.out.log"
$ApiErrLog = Join-Path $LogDir "api.err.log"
$WebOutLog = Join-Path $LogDir "web.out.log"
$WebErrLog = Join-Path $LogDir "web.err.log"
$CredentialDir = Join-Path $Root ".chronovita-local"
$PublicationCredentialPath = Join-Path $CredentialDir "content-history-token.dpapi"

function Write-Step {
  param([string] $Message)
  Write-Host ""
  Write-Host "== $Message ==" -ForegroundColor Cyan
}

function Test-Command {
  param([string] $Name)
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-ExpectedAppVersion {
  if (-not (Test-Path -LiteralPath $VersionFile -PathType Leaf)) {
    throw "Application version file was not found: $VersionFile"
  }
  $source = Get-Content -LiteralPath $VersionFile -Raw
  $match = [regex]::Match(
    $source,
    '(?m)^APP_VERSION\s*=\s*"(?<version>[0-9]+\.[0-9]+\.[0-9]+)"\s*$'
  )
  if (-not $match.Success) {
    throw "Application version could not be read from: $VersionFile"
  }
  return $match.Groups["version"].Value
}

function Test-SupportedPython {
  param(
    [string] $FilePath,
    [string[]] $PrefixArguments = @()
  )

  $previousErrorActionPreference = $ErrorActionPreference
  try {
    # Windows PowerShell 5.1 can promote py.exe's missing-runtime stderr to a
    # terminating NativeCommandError while probing the next explicit version.
    $ErrorActionPreference = "Continue"
    & $FilePath @PrefixArguments -c `
      "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) else 1)" `
      *> $null
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
  return $exitCode -eq 0
}

function Get-SupportedPython {
  $pythonCommand = Get-Command "python.exe" -ErrorAction SilentlyContinue
  if (
    $pythonCommand `
    -and (Test-SupportedPython $pythonCommand.Source)
  ) {
    return [PSCustomObject] @{
      FilePath = $pythonCommand.Source
      PrefixArguments = @()
      Label = "python"
    }
  }

  $pyCommand = Get-Command "py.exe" -ErrorAction SilentlyContinue
  if ($pyCommand) {
    foreach ($selector in @("-3.13", "-3.12", "-3.11")) {
      if (Test-SupportedPython $pyCommand.Source @($selector)) {
        return [PSCustomObject] @{
          FilePath = $pyCommand.Source
          PrefixArguments = @($selector)
          Label = "py $selector"
        }
      }
    }
  }

  throw "Python 3.11, 3.12, or 3.13 was not found. Install a supported Python version and run this launcher again."
}

function Test-SupportedNode {
  param([string] $FilePath)

  $previousErrorActionPreference = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    & $FilePath -e `
      "const [major, minor] = process.versions.node.split('.').map(Number); process.exit((major === 20 && minor >= 19) || (major === 22 && minor >= 12) || major > 22 ? 0 : 1)" `
      *> $null
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
  return $exitCode -eq 0
}

function Repair-DuplicateProcessEnvironment {
  $entries = @([System.Environment]::GetEnvironmentVariables().GetEnumerator())
  $duplicates = $entries |
    Group-Object { $_.Key.ToString().ToUpperInvariant() } |
    Where-Object { $_.Count -gt 1 }

  foreach ($duplicate in $duplicates) {
    $preferred = @($duplicate.Group | Where-Object {
      $_.Key.ToString() -ceq $_.Key.ToString().ToUpperInvariant()
    } | Select-Object -First 1)
    if ($preferred.Count -eq 0) {
      $preferred = @($duplicate.Group | Select-Object -First 1)
    }
    foreach ($entry in $duplicate.Group) {
      [System.Environment]::SetEnvironmentVariable(
        $entry.Key.ToString(),
        $null,
        [System.EnvironmentVariableTarget]::Process
      )
    }
    [System.Environment]::SetEnvironmentVariable(
      $preferred[0].Key.ToString(),
      $preferred[0].Value.ToString(),
      [System.EnvironmentVariableTarget]::Process
    )
  }
}

function Quote-ProcessArgument {
  param([string] $Value)
  return '"' + $Value + '"'
}

function Convert-SecureValueToPlainText {
  param([Security.SecureString] $Value)

  $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
  try {
    return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
  }
}

function Import-LocalContentHistoryCredential {
  if (-not (Test-Path -LiteralPath $PublicationCredentialPath -PathType Leaf)) {
    Write-Host "Course history submission is not configured. Local editing and ZIP export remain available."
    return
  }

  try {
    $encrypted = (Get-Content -LiteralPath $PublicationCredentialPath -Raw).Trim()
    if ([string]::IsNullOrWhiteSpace($encrypted) -or $encrypted.Length -gt 16384) {
      throw "The encrypted credential file is empty or too large."
    }
    $secureToken = ConvertTo-SecureString $encrypted
    $plainToken = Convert-SecureValueToPlainText $secureToken
    try {
      if (
        [string]::IsNullOrWhiteSpace($plainToken) `
        -or $plainToken.Length -lt 20 `
        -or $plainToken.Length -gt 512 `
        -or $plainToken -notmatch '^[\x21-\x7E]+$'
      ) {
        throw "The decrypted credential is invalid."
      }
      $env:CHRONO_GITHUB_PUBLICATION_TOKEN = $plainToken
      $env:CHRONO_GITHUB_PUBLICATION_ENABLED = "true"
    } finally {
      $plainToken = $null
    }
    Write-Host "Course history submission credential loaded for the API process." -ForegroundColor Green
  } catch {
    throw "The local course submission credential could not be read. Run scripts\configure-content-history.cmd to replace it."
  }
}

function Clear-TransientContentHistoryCredential {
  [System.Environment]::SetEnvironmentVariable(
    "CHRONO_GITHUB_PUBLICATION_TOKEN",
    $null,
    [System.EnvironmentVariableTarget]::Process
  )
}

function Set-LocalRuntimeEnvironment {
  $inheritedChronoKeys = @(
    [System.Environment]::GetEnvironmentVariables().Keys |
      Where-Object { $_.ToString().StartsWith("CHRONO_", [System.StringComparison]::OrdinalIgnoreCase) }
  )
  foreach ($key in $inheritedChronoKeys) {
    [System.Environment]::SetEnvironmentVariable(
      $key.ToString(),
      $null,
      [System.EnvironmentVariableTarget]::Process
    )
  }

  $env:CHRONO_DISABLE_DOTENV = "true"
  $env:CHRONO_RUNTIME_PROFILE = "local"
  $env:CHRONO_DEBUG = "true"
  $env:CHRONO_CORS_ORIGINS = '["http://127.0.0.1:5173"]'
  $env:CHRONO_TRUSTED_HOSTS = '["127.0.0.1","localhost"]'
  $env:CHRONO_SQLITE_PATH = "data/chronovita.db"
  $env:CHRONO_DATABASE_MIGRATION_MODE = "apply-safe"
  $env:CHRONO_CONTENT_ROOT = "content"
  $env:CHRONO_AUTH_MODE = "legacy-local"
  $env:CHRONO_AUTH_SESSION_TTL_SECONDS = "28800"
  $env:CHRONO_AUTH_COOKIE_NAME = "chronovita_session"
  $env:CHRONO_AUTH_COOKIE_SECURE = "false"
  $env:CHRONO_AUTH_LOGIN_RATE_LIMIT_ATTEMPTS = "10"
  $env:CHRONO_AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS = "60"
  $env:CHRONO_AUTH_LOGIN_RATE_LIMIT_MAX_CLIENTS = "10000"
  $env:CHRONO_GAME_CATALOG_PATH = "scenarios/catalog.v1.json"
  $env:CHRONO_GAME_USER_ID = "local-student"
  $env:CHRONO_LLM_PROVIDER = "mock"
  $env:CHRONO_LLM_STRUCTURED_TIMEOUT_SECONDS = "12"
  $env:CHRONO_LLM_STRUCTURED_MAX_TOKENS = "512"
  $env:CHRONO_LLM_STRUCTURED_MAX_RESPONSE_BYTES = "32768"
  $env:CHRONO_ADMIN_ACTOR = "local-admin"
  $env:VITE_API_PROXY_TARGET = "http://127.0.0.1:8000"

  $tokenBytes = New-Object byte[] 32
  $tokenGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $tokenGenerator.GetBytes($tokenBytes)
  } finally {
    $tokenGenerator.Dispose()
  }
  $env:CHRONO_ADMIN_TOKEN = [Convert]::ToBase64String($tokenBytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
  $env:VITE_ADMIN_TOKEN = $env:CHRONO_ADMIN_TOKEN
}

function Invoke-Checked {
  param(
    [string] $Title,
    [string] $FilePath,
    [string[]] $Arguments,
    [string] $WorkingDirectory = $Root
  )

  Write-Host $Title
  $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -NoNewWindow -Wait -PassThru
  if ($process.ExitCode -ne 0) {
    throw "$Title failed with exit code $($process.ExitCode)."
  }
}

function Invoke-NpmChecked {
  param(
    [string] $Title,
    [string[]] $Arguments
  )

  $npmCommand = Get-Command "npm.cmd" -ErrorAction Stop
  Write-Host $Title
  Push-Location $WebDir
  try {
    & $npmCommand.Source @Arguments
    if ($LASTEXITCODE -ne 0) {
      throw "$Title failed with exit code $LASTEXITCODE."
    }
  } finally {
    Pop-Location
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

function Open-ExistingEditor {
  $apiInUse = Test-LocalPort $ApiHost $ApiPort
  $webInUse = Test-LocalPort $WebHost $WebPort
  if (-not $apiInUse -and -not $webInUse) {
    return $false
  }
  if ($apiInUse -ne $webInUse) {
    throw "Only one launcher port is in use. Close the process on ports $ApiPort/$WebPort, then run the launcher again."
  }

  try {
    $health = Invoke-RestMethod -Method Get -Uri "http://$ApiHost`:$ApiPort/healthz" -TimeoutSec 3
    $web = Invoke-WebRequest -UseBasicParsing -Method Get -Uri $EditorUrl -TimeoutSec 3
  } catch {
    throw "Ports $ApiPort and $WebPort are occupied by services that are not a healthy Chronovita editor."
  }
  if ($health.status -ne "alive" -or $web.StatusCode -ne 200 -or $web.Content -notmatch "Chronovita") {
    throw "Ports $ApiPort and $WebPort are occupied by services that are not a healthy Chronovita editor."
  }
  if ([string]$health.version -ne $ExpectedAppVersion) {
    throw "A different Chronovita version is already using ports $ApiPort/$WebPort. Stop it before starting V$ExpectedAppVersion."
  }

  Write-Host "Chronovita V$ExpectedAppVersion is already running. Opening the existing editor." -ForegroundColor Green
  if (-not $SkipBrowser) {
    Start-Process $EditorUrl
  }
  return $true
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

function Wait-EditorRuntime {
  param(
    [System.Diagnostics.Process] $ApiProcess,
    [System.Diagnostics.Process] $WebProcess
  )

  for ($i = 0; $i -lt 40; $i += 1) {
    if ($ApiProcess.HasExited -or $WebProcess.HasExited) {
      throw "A launcher process exited before the editor became ready."
    }
    try {
      $ready = Invoke-RestMethod `
        -Method Get `
        -Uri "http://$ApiHost`:$ApiPort/readyz" `
        -TimeoutSec 3
      $editor = Invoke-WebRequest `
        -UseBasicParsing `
        -Method Get `
        -Uri $EditorUrl `
        -TimeoutSec 3
      if (
        $ready.status -eq "ready" `
        -and $editor.StatusCode -eq 200 `
        -and $editor.Content -match "Chronovita"
      ) {
        Write-Host "API and editor HTTP services are ready." -ForegroundColor Green
        return
      }
    } catch {
      # The services can accept TCP connections before application startup ends.
    }
    Start-Sleep -Milliseconds 500
  }

  Write-Host "The editor did not pass its HTTP readiness checks." -ForegroundColor Red
  foreach ($errorLog in @($ApiErrLog, $WebErrLog)) {
    if (Test-Path $errorLog) {
      Get-Content -LiteralPath $errorLog -Tail 60
    }
  }
  throw "Chronovita teacher editor did not become ready."
}

function Stop-StartedProcessTree {
  param([System.Diagnostics.Process] $Process)
  if (-not $Process -or $Process.HasExited) {
    return
  }
  $taskkill = Join-Path $env:SystemRoot "System32\taskkill.exe"
  try {
    & $taskkill /PID "$($Process.Id)" /T /F 2>$null | Out-Null
  } catch {
    Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
  }
}

function Ensure-PythonEnvironment {
  if (Test-Path $PythonExe) {
    if (-not (Test-SupportedPython $PythonExe)) {
      throw "The existing .venv does not use Python 3.11-3.13. Move or remove .venv, then run this launcher again."
    }
    Write-Host "Python virtualenv found: $PythonExe"
    return
  }

  Write-Step "Preparing Python virtualenv"

  $pythonRuntime = Get-SupportedPython
  $venvArguments = @($pythonRuntime.PrefixArguments) + @(
    "-m",
    "venv",
    (Quote-ProcessArgument $VenvDir)
  )
  Invoke-Checked "Creating .venv with $($pythonRuntime.Label)" `
    $pythonRuntime.FilePath `
    $venvArguments

  if (-not (Test-Path $PythonExe)) {
    throw "Virtualenv was created, but $PythonExe was not found."
  }
}

function Ensure-ApiDependencies {
  if (-not (Test-Path $Requirements)) {
    throw "API dependency lock file was not found: $Requirements"
  }

  $requirementsHash = (Get-FileHash -LiteralPath $Requirements -Algorithm SHA256).Hash
  if (Test-Path $ApiDepsStamp) {
    $installedHash = (Get-Content -LiteralPath $ApiDepsStamp -Raw).Trim()
    if ($installedHash -eq $requirementsHash) {
      & $PythonExe -c "import fastapi, uvicorn, pydantic_settings"
      if ($LASTEXITCODE -eq 0) {
        Write-Host "API dependencies found: $ApiDepsStamp"
        return
      }
    }
  }

  Write-Step "Installing API dependencies"
  Invoke-Checked "Installing hash-locked apps\api requirements" $PythonExe @(
    "-m",
    "pip",
    "install",
    "--disable-pip-version-check",
    "--require-hashes",
    "-r",
    (Quote-ProcessArgument $Requirements)
  )
  Set-Content -LiteralPath $ApiDepsStamp -Value $requirementsHash -Encoding ASCII
}

function Ensure-WebDependencies {
  if (-not (Test-Path (Join-Path $WebDir "package.json"))) {
    throw "Web package.json was not found: $WebDir"
  }

  if (-not (Test-Command "npm")) {
    throw "npm was not found. Please install Node.js 20.19+ or 22.12+ and run this launcher again."
  }

  $nodeCommand = Get-Command "node.exe" -ErrorAction SilentlyContinue
  if (-not $nodeCommand -or -not (Test-SupportedNode $nodeCommand.Source)) {
    throw "Node.js 20.19+ or 22.12+ is required. Install a supported Node.js LTS version and run this launcher again."
  }

  $viteBin = Join-Path $WebDir "node_modules\.bin\vite.cmd"
  if (Test-Path $viteBin) {
    Write-Host "Web dependencies found: apps\web\node_modules"
    return
  }

  Write-Step "Installing web dependencies"
  Invoke-NpmChecked "Running npm ci in apps\web" @(
    "ci",
    "--no-audit",
    "--no-fund"
  )
}

function Test-WebBuild {
  Write-Step "Validating web editor build"
  Invoke-NpmChecked "Running npm build in apps\web" @("run", "build")
}

function Start-Api {
  if (Test-LocalPort $ApiHost $ApiPort) {
    throw "API port $ApiPort became occupied before startup."
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
    throw "Web port $WebPort became occupied before startup."
  }

  Write-Step "Starting web editor"
  $process = Start-Process -FilePath "cmd.exe" `
    -ArgumentList @("/c", "npm run preview -- --host $WebHost --port $WebPort --strictPort") `
    -WorkingDirectory $WebDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $WebOutLog `
    -RedirectStandardError $WebErrLog `
    -PassThru
  Write-Host "Web process started: $($process.Id)"
  return $process
}

$apiProcess = $null
$webProcess = $null
$ExpectedAppVersion = Get-ExpectedAppVersion

try {
  New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

  Write-Host "Chronovita teacher editor launcher"
  Write-Host "Project root: $Root"

  Repair-DuplicateProcessEnvironment

  if (Open-ExistingEditor) {
    exit 0
  }

  Set-LocalRuntimeEnvironment

  Ensure-PythonEnvironment
  Ensure-ApiDependencies
  Ensure-WebDependencies
  Test-WebBuild

  Import-LocalContentHistoryCredential
  $apiProcess = Start-Api
  Clear-TransientContentHistoryCredential
  $webProcess = Start-Web

  Wait-LocalPort "API" $ApiHost $ApiPort $apiProcess $ApiErrLog
  Wait-LocalPort "Web editor" $WebHost $WebPort $webProcess $WebErrLog
  Wait-EditorRuntime $apiProcess $webProcess

  Write-Step "Opening editor"
  Write-Host $EditorUrl -ForegroundColor Green
  if (-not $SkipBrowser) {
    Start-Process $EditorUrl
  }
  Write-Host ""
  Write-Host "Services are ready. Keep this window open if you want to read the launch log."
  Write-Host "Runtime logs are saved in: $LogDir"
} catch {
  Stop-StartedProcessTree $webProcess
  Stop-StartedProcessTree $apiProcess
  Write-Host ""
  Write-Host "Launch failed:" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  Write-Host ""
  Write-Host "Please send the logs in this folder to the developer team:"
  Write-Host $LogDir
  exit 1
}
