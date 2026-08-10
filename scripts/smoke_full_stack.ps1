$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$apiPort = Get-DotEnvInt -Name "API_HOST_PORT" -Default 8000
$frontendPort = Get-DotEnvInt -Name "FRONTEND_HOST_PORT" -Default 5173
$deadline = (Get-Date).AddMinutes(2)

Wait-HttpReady -Name "API live" -Uri "http://127.0.0.1:$apiPort/health/live" -Deadline $deadline
Wait-HttpReady -Name "API ready" -Uri "http://127.0.0.1:$apiPort/health/ready" -Deadline $deadline
Wait-HttpReady -Name "Frontend Nginx" -Uri "http://127.0.0.1:$frontendPort/healthz" -Deadline $deadline
Wait-HttpReady -Name "Frontend -> API proxy" -Uri "http://127.0.0.1:$frontendPort/health/live" -Deadline $deadline

$homeResponse = Invoke-WebRequest -Uri "http://127.0.0.1:$frontendPort/" -UseBasicParsing -TimeoutSec 10
if ($homeResponse.Content -notmatch "Shopkeeper Agent Rebuild") {
    throw "Frontend HTML does not contain the expected application title"
}

Write-Host "[OK] Full stack smoke test passed." -ForegroundColor Green
