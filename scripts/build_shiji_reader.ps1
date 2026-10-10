param()

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "== Building migrated 史记 reader ==" -ForegroundColor Cyan
& npm --prefix (Join-Path $Root "apps/web") run build:reader
if ($LASTEXITCODE -ne 0) { throw "史记阅读器构建失败" }
