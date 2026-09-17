param()

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReaderRoot = Join-Path $Root "apps\shiji-reader"
$StaticRoot = Join-Path $Root "apps\web\public\shiji-reader"

Write-Host "== Building migrated 史记 reader ==" -ForegroundColor Cyan
& npm --prefix $ReaderRoot ci --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw "史记阅读器依赖安装失败" }
& npm --prefix $ReaderRoot run build
if ($LASTEXITCODE -ne 0) { throw "史记阅读器构建失败" }
New-Item -ItemType Directory -Force -Path $StaticRoot | Out-Null
Copy-Item -Path (Join-Path $ReaderRoot "dist\*") -Destination $StaticRoot -Recurse -Force
Write-Host "史记阅读器已写入 apps/web/public/shiji-reader" -ForegroundColor Green
