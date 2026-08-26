param(
  [ValidateRange(1024, 65535)]
  [int] $Port = 8765,
  [switch] $KeepArtifacts
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$WebRoot = Join-Path $Root "apps\web"
$WebDist = Join-Path $WebRoot "dist"
$ContentRoot = Join-Path $Root "content"
$QaRoot = Join-Path $Root ".chronovita-local-e2e"
$Database = Join-Path $QaRoot "classroom.db"
$RagIndex = Join-Path $QaRoot "rag.db"
$MissingModel = Join-Path $QaRoot "missing-model"
$Stdout = Join-Path $QaRoot "api.stdout.log"
$Stderr = Join-Path $QaRoot "api.stderr.log"
$BaseUrl = "http://127.0.0.1`:$Port"

function Test-LocalPort {
  param([int] $TargetPort)
  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $result = $client.BeginConnect("127.0.0.1", $TargetPort, $null, $null)
    if (-not $result.AsyncWaitHandle.WaitOne(300)) { return $false }
    $client.EndConnect($result)
    return $true
  } catch {
    return $false
  } finally {
    $client.Dispose()
  }
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "Python environment is missing: $Python"
}
if (-not (Test-Path -LiteralPath $WebDist -PathType Container)) {
  throw "Built web app is missing. Run npm --prefix apps/web run build first."
}
if (Test-LocalPort $Port) {
  throw "Local E2E port $Port is already in use."
}
if (Test-Path -LiteralPath $QaRoot) {
  throw "Local E2E directory already exists: $QaRoot"
}

New-Item -ItemType Directory -Path $QaRoot | Out-Null
$adminPassword = "Local-admin-$([guid]::NewGuid().ToString('N'))-Aa1!"
$userPassword = "Local-student-$([guid]::NewGuid().ToString('N'))-Bb2!"

$env:CHRONO_DISABLE_DOTENV = "true"
$env:CHRONO_RUNTIME_PROFILE = "local"
$env:CHRONO_API_WORKER_COUNT = "1"
$env:CHRONO_DEBUG = "false"
$env:CHRONO_AUTH_MODE = "accounts"
$env:CHRONO_AUTH_COOKIE_SECURE = "false"
$env:CHRONO_AUTH_BOOTSTRAP_USERNAME = "classroom.admin"
$env:CHRONO_AUTH_BOOTSTRAP_DISPLAY_NAME = "Classroom Local E2E Admin"
$env:CHRONO_AUTH_BOOTSTRAP_PASSWORD = $adminPassword
$env:CHRONO_AUTH_LOGIN_RATE_LIMIT_ATTEMPTS = "100"
$env:CHRONO_GITHUB_PUBLICATION_ENABLED = "false"
$env:CHRONO_RAG_VECTOR_ENABLED = "false"
$env:CHRONO_LLM_PROVIDER = "mock"
$env:CHRONO_SERVE_WEB_APP = "true"
$env:CHRONO_SQLITE_PATH = $Database
$env:CHRONO_RAG_INDEX_PATH = $RagIndex
$env:CHRONO_RAG_MODEL_ROOT = $MissingModel
$env:CHRONO_CONTENT_ROOT = $ContentRoot
$env:CHRONO_WEB_DIST_ROOT = $WebDist
$env:CHRONO_CORS_ORIGINS = ConvertTo-Json -Compress @($BaseUrl, "http://localhost`:$Port")
$env:CHRONO_TRUSTED_HOSTS = '["127.0.0.1","localhost"]'
$env:PYTHONPATH = "$Root;$(Join-Path $Root 'apps\api')"
$env:CHRONO_E2E_BASE_URL = $BaseUrl
$env:CHRONO_E2E_BROWSER_CHANNEL = "msedge"
$env:CHRONO_E2E_ADMIN_USERNAME = "classroom.admin"
$env:CHRONO_E2E_ADMIN_PASSWORD = $adminPassword
$env:CHRONO_E2E_USER_PASSWORD = $userPassword

$server = $null
try {
  $server = Start-Process -FilePath $Python `
    -ArgumentList @(
      "-m", "uvicorn", "main:app", "--app-dir", "apps/api",
      "--host", "127.0.0.1", "--port", "$Port", "--workers", "1"
    ) `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $Stdout `
    -RedirectStandardError $Stderr `
    -PassThru

  $ready = $false
  foreach ($attempt in 1..120) {
    if ($server.HasExited) {
      $details = (Get-Content -LiteralPath $Stderr -Raw -ErrorAction SilentlyContinue).Trim()
      throw "Local E2E service exited before readiness. $details"
    }
    try {
      $health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/healthz" -TimeoutSec 2
      if ($health.status -eq "alive") {
        $ready = $true
        break
      }
    } catch {
      Start-Sleep -Milliseconds 250
    }
  }
  if (-not $ready) {
    throw "Local E2E service did not become ready. See $Stderr"
  }

  $env:CHRONO_AUTH_BOOTSTRAP_PASSWORD = $null
  & npm.cmd --prefix $WebRoot run test:e2e
  if ($LASTEXITCODE -ne 0) {
    throw "Student classroom Playwright chain failed with $LASTEXITCODE."
  }
} finally {
  if ($null -ne $server -and -not $server.HasExited) {
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    $server.WaitForExit(10000) | Out-Null
  }
  $env:CHRONO_AUTH_BOOTSTRAP_PASSWORD = $null
  $env:CHRONO_E2E_ADMIN_PASSWORD = $null
  $env:CHRONO_E2E_USER_PASSWORD = $null

  if (-not $KeepArtifacts -and (Test-Path -LiteralPath $QaRoot)) {
    $resolvedQaRoot = [System.IO.Path]::GetFullPath($QaRoot)
    $resolvedRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    if (-not $resolvedQaRoot.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Refusing to clean local E2E data outside the workspace: $resolvedQaRoot"
    }
    Remove-Item -LiteralPath $resolvedQaRoot -Recurse -Force
  }
}
