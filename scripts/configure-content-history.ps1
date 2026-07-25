param(
  [switch] $Remove,
  [Security.SecureString] $Token,
  [string] $CredentialRoot = "",
  [switch] $NonInteractive,
  [switch] $ContinueCurrentLaunch
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if ([string]::IsNullOrWhiteSpace($CredentialRoot)) {
  $CredentialRoot = Join-Path $ProjectRoot ".chronovita-local"
}
$CredentialPath = Join-Path $CredentialRoot "content-history-token.dpapi"

function Convert-SecureValueToPlainText {
  param([Security.SecureString] $Value)

  $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
  try {
    return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
  }
}

function Test-TruthyEnvironmentValue {
  param([string] $Name)

  $value = [Environment]::GetEnvironmentVariable($Name)
  if ([string]::IsNullOrWhiteSpace($value)) {
    return $false
  }
  return @("0", "false", "no", "off") -notcontains $value.Trim().ToLowerInvariant()
}

function Test-InteractiveInputAvailable {
  if ($NonInteractive -or (Test-TruthyEnvironmentValue "CI")) {
    return $false
  }
  if (-not [Environment]::UserInteractive) {
    return $false
  }
  try {
    return -not [Console]::IsInputRedirected
  } catch {
    return $false
  }
}

try {
  if ($Remove) {
    Remove-Item -LiteralPath $CredentialPath -Force -ErrorAction SilentlyContinue
    Write-Host "The local content submission credential was removed." -ForegroundColor Green
    return
  }

  if ($null -eq $Token) {
    if (-not (Test-InteractiveInputAvailable)) {
      throw "No token was supplied and secure input is unavailable. Run this script interactively, or pass -Token as a SecureString."
    }
    Write-Host "Chronovita content history submission setup"
    Write-Host ""
    Write-Host "Paste the fine-grained GitHub token supplied by the project administrator."
    Write-Host "The token is encrypted for this Windows account and is never written as plain text."
    $Token = Read-Host "Token" -AsSecureString
  }

  $plainText = Convert-SecureValueToPlainText $Token
  try {
    if (
      [string]::IsNullOrWhiteSpace($plainText) `
      -or $plainText.Length -lt 20 `
      -or $plainText.Length -gt 512 `
      -or $plainText -notmatch '^[\x21-\x7E]+$'
    ) {
      throw "The supplied token is not a valid non-empty ASCII credential."
    }
  } finally {
    $plainText = $null
  }

  New-Item -ItemType Directory -Path $CredentialRoot -Force | Out-Null
  $encrypted = ConvertFrom-SecureString -SecureString $Token
  $temporaryPath = "$CredentialPath.$PID.tmp"
  try {
    [IO.File]::WriteAllText(
      $temporaryPath,
      $encrypted + [Environment]::NewLine,
      [Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $temporaryPath -Destination $CredentialPath -Force
  } finally {
    Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
  }

  Write-Host ""
  Write-Host "Content history submission is configured for this Windows account." -ForegroundColor Green
  if ($ContinueCurrentLaunch) {
    Write-Host "The credential will be used by the editor starting now."
  } else {
    Write-Host "Restart the Chronovita editor before submitting content."
  }
  Write-Host "No Git installation or GitHub command line is required."
} catch {
  Write-Host ""
  Write-Host "Configuration failed:" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  throw
}
