$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

if (-not (Test-Path $script:EnvFile)) {
    throw ".env does not exist"
}

# Do not pass -v: all database, index, vector, and model volumes must survive.
Invoke-ShopkeeperCompose down --remove-orphans
Write-Host "[OK] Stack stopped. Persistent volumes were preserved." -ForegroundColor Green
