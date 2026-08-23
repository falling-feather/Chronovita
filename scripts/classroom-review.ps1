param(
  [ValidateRange(1024, 65535)]
  [int] $ApiPort = 8010,
  [ValidateRange(1024, 65535)]
  [int] $WebPort = 5174,
  [string] $DatabasePath = "data\chronovita.db",
  [switch] $LexicalOnly,
  [switch] $SkipBrowser
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"
$WebDir = Join-Path $Root "apps\web"
$ModelRoot = Join-Path $Root "distribution\models\BAAI-bge-small-zh-v1.5"
$RuntimeDir = Join-Path $Root ".chronovita-review"
$LogDir = Join-Path $RuntimeDir "logs"
$RuntimeState = Join-Path $RuntimeDir "runtime.json"
$ApiUrl = "http://127.0.0.1`:$ApiPort"
$WebUrl = "http://127.0.0.1`:$WebPort"
$ReviewUrl = "$WebUrl/login?next=%2F"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ApiOutLog = Join-Path $LogDir "api-$stamp.out.log"
$ApiErrLog = Join-Path $LogDir "api-$stamp.err.log"
$WebOutLog = Join-Path $LogDir "web-$stamp.out.log"
$WebErrLog = Join-Path $LogDir "web-$stamp.err.log"

function Write-Step {
  param([string] $Message)
  Write-Host ""
  Write-Host "== $Message ==" -ForegroundColor Cyan
}

function Resolve-ReviewPath {
  param([string] $Value)
  if ([System.IO.Path]::IsPathRooted($Value)) {
    return [System.IO.Path]::GetFullPath($Value)
  }
  return [System.IO.Path]::GetFullPath((Join-Path $Root $Value))
}

function Test-LocalPort {
  param([int] $Port)
  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $result = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
    if (-not $result.AsyncWaitHandle.WaitOne(300)) {
      return $false
    }
    $client.EndConnect($result)
    return $true
  } catch {
    return $false
  } finally {
    $client.Dispose()
  }
}

function Wait-HttpReady {
  param(
    [string] $Label,
    [string] $Url,
    [System.Diagnostics.Process] $Process,
    [string] $ErrorLog
  )
  $deadline = [DateTime]::UtcNow.AddSeconds(90)
  while ([DateTime]::UtcNow -lt $deadline) {
    if ($Process.HasExited) {
      $detail = if (Test-Path -LiteralPath $ErrorLog) {
        (Get-Content -LiteralPath $ErrorLog -Raw -ErrorAction SilentlyContinue).Trim()
      } else { "" }
      throw "$Label exited before becoming ready. $detail"
    }
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
        return
      }
    } catch {
      Start-Sleep -Milliseconds 300
    }
  }
  throw "$Label did not become ready within 90 seconds. See $ErrorLog"
}

function Stop-StartedProcess {
  param([System.Diagnostics.Process] $Process)
  if ($null -ne $Process -and -not $Process.HasExited) {
    Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
  }
}

if ($ApiPort -eq $WebPort) {
  throw "API and web review ports must be different."
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
  throw "Python environment is missing: $PythonExe"
}
if (-not (Test-Path -LiteralPath (Join-Path $WebDir "node_modules\.bin\vite.cmd") -PathType Leaf)) {
  throw "Web dependencies are missing. Run npm ci in apps\web first."
}
if (Test-LocalPort $ApiPort) {
  throw "Review API port $ApiPort is already in use. Choose -ApiPort explicitly."
}
if (Test-LocalPort $WebPort) {
  throw "Review web port $WebPort is already in use. Choose -WebPort explicitly."
}

$ResolvedDatabasePath = Resolve-ReviewPath $DatabasePath
$RagIndexPath = Join-Path $RuntimeDir "rag-index-v1.sqlite3"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ResolvedDatabasePath) | Out-Null

$env:CHRONO_DISABLE_DOTENV = "true"
$env:CHRONO_RUNTIME_PROFILE = "local"
$env:CHRONO_API_WORKER_COUNT = "1"
$env:CHRONO_DEBUG = "false"
$env:CHRONO_CORS_ORIGINS = ConvertTo-Json -InputObject @(
  $WebUrl,
  "http://localhost`:$WebPort"
) -Compress
$env:CHRONO_TRUSTED_HOSTS = '["127.0.0.1","localhost"]'
$env:CHRONO_SQLITE_PATH = $ResolvedDatabasePath
$env:CHRONO_DATABASE_MIGRATION_MODE = "apply-safe"
$env:CHRONO_CONTENT_ROOT = (Join-Path $Root "content")
$env:CHRONO_SERVE_WEB_APP = "false"
$env:CHRONO_AUTH_MODE = "accounts"
$env:CHRONO_AUTH_COOKIE_SECURE = "false"
$env:CHRONO_GITHUB_PUBLICATION_ENABLED = "false"
$env:CHRONO_RAG_INDEX_PATH = $RagIndexPath
$env:CHRONO_RAG_MODEL_ROOT = $ModelRoot
$env:CHRONO_RAG_VECTOR_ENABLED = if ($LexicalOnly) { "false" } else { "true" }
$env:VITE_API_PROXY_TARGET = $ApiUrl
if ([string]::IsNullOrWhiteSpace($env:CHRONO_LLM_PROVIDER)) {
  $env:CHRONO_LLM_PROVIDER = "mock"
}

if (-not $LexicalOnly) {
  Write-Step "Verifying packaged BGE vector model"
  & $PythonExe (Join-Path $Root "scripts\prepare_rag_model.py") `
    --verify-only --target $ModelRoot *> $null
  if ($LASTEXITCODE -ne 0) {
    throw (
      "The packaged BGE model is missing or damaged. " +
      "Repair distribution\models first, or pass -LexicalOnly explicitly."
    )
  }
}

$apiProcess = $null
$webProcess = $null
try {
  Write-Step "Starting accounts-mode review API"
  $apiProcess = Start-Process -FilePath $PythonExe `
    -ArgumentList @(
      "-m", "uvicorn", "apps.api.main:app",
      "--host", "127.0.0.1", "--port", "$ApiPort", "--workers", "1"
    ) `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $ApiOutLog `
    -RedirectStandardError $ApiErrLog `
    -PassThru

  Write-Step "Starting Vite review site"
  $webProcess = Start-Process -FilePath "cmd.exe" `
    -ArgumentList @(
      "/d", "/s", "/c",
      "npm run dev -- --host 127.0.0.1 --port $WebPort --strictPort"
    ) `
    -WorkingDirectory $WebDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $WebOutLog `
    -RedirectStandardError $WebErrLog `
    -PassThru

  Wait-HttpReady "Review API" "$ApiUrl/readyz" $apiProcess $ApiErrLog
  Wait-HttpReady "Review web" $WebUrl $webProcess $WebErrLog

  [PSCustomObject]@{
    schema_version = "chronovita-review-runtime/v1"
    api_pid = $apiProcess.Id
    web_pid = $webProcess.Id
    api_port = $ApiPort
    web_port = $WebPort
    database_path = $ResolvedDatabasePath
    retrieval_mode = if ($LexicalOnly) { "lexical" } else { "hybrid" }
    started_at = [DateTime]::UtcNow.ToString("o")
  } | ConvertTo-Json | Set-Content -LiteralPath $RuntimeState -Encoding UTF8

  Write-Step "Chronovita review ready"
  Write-Host "Review URL: $ReviewUrl" -ForegroundColor Green
  Write-Host "Trusted Origin: $WebUrl"
  Write-Host "RAG mode: $(if ($LexicalOnly) { 'lexical (explicit)' } else { 'hybrid BGE + FTS5' })"
  Write-Host "Stop with: .\scripts\stop-classroom-review.ps1"
  if (-not $SkipBrowser) {
    Start-Process $ReviewUrl
  }
} catch {
  Stop-StartedProcess $webProcess
  Stop-StartedProcess $apiProcess
  Write-Host $_.Exception.Message -ForegroundColor Red
  throw
}
