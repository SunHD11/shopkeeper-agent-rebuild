$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

if (-not (Test-Path $script:EnvFile)) {
    Write-Host "[FAIL] .env does not exist. Copy .env.example to .env first." -ForegroundColor Red
    exit 1
}

$values = Get-DotEnvValues
$required = @(
    "MYSQL_ROOT_PASSWORD",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "LLM_API_KEY"
)
$invalid = @()

foreach ($name in $required) {
    $value = $values[$name]
    if (-not $value -or $value -match "(?i)replace_with|change_me|your_.*key|example") {
        $invalid += $name
    }
}

if ($invalid.Count -gt 0) {
    Write-Host "[FAIL] Set real values in .env for: $($invalid -join ', ')" -ForegroundColor Red
    exit 1
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "[FAIL] Docker CLI is not installed or not in PATH." -ForegroundColor Red
    exit 1
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Docker Desktop is not running." -ForegroundColor Red
    exit 1
}

docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Docker Compose v2 is unavailable." -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Environment and Docker prerequisites are valid." -ForegroundColor Green
