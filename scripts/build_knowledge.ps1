$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

& (Join-Path $PSScriptRoot "validate_env.ps1")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Building the metadata knowledge base inside the API image..." -ForegroundColor Cyan
Invoke-ShopkeeperCompose run --rm api `
    python -m app.scripts.build_meta_knowledge -c conf/meta_config.yaml

Write-Host "[OK] Metadata knowledge base build completed." -ForegroundColor Green
