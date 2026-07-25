param(
  [switch] $Remove,
  [Security.SecureString] $Token,
  [string] $CredentialRoot = ""
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

try {
  if ($Remove) {
    Remove-Item -LiteralPath $CredentialPath -Force -ErrorAction SilentlyContinue
    Write-Host "The local course submission credential was removed." -ForegroundColor Green
    return
  }

  if ($null -eq $Token) {
    Write-Host "Chronovita course history submission setup"
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
  Write-Host "Course history submission is configured for this Windows account." -ForegroundColor Green
  Write-Host "Restart the Chronovita editor before submitting a course."
  Write-Host "No Git installation or GitHub command line is required."
} catch {
  Write-Host ""
  Write-Host "Configuration failed:" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  throw
}
