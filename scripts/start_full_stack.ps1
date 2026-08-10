param(
    [switch]$SkipBuild,
    [switch]$SkipKnowledgeBuild,
    [ValidateRange(60, 3600)]
    [int]$TimeoutSeconds = 1800
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

& (Join-Path $PSScriptRoot "validate_env.ps1")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Invoke-ShopkeeperCompose config --quiet

$upArguments = @("up", "-d")
if (-not $SkipBuild) {
    $upArguments += "--build"
}

Write-Host "Starting the complete Shopkeeper Agent stack..." -ForegroundColor Cyan
Invoke-ShopkeeperCompose @upArguments

$apiPort = Get-DotEnvInt -Name "API_HOST_PORT" -Default 8000
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
try {
    Wait-HttpReady `
        -Name "API and five dependencies" `
        -Uri "http://127.0.0.1:$apiPort/health/ready" `
        -Deadline $deadline
}
catch {
    Write-Host "The stack did not become ready. Current status:" -ForegroundColor Red
    Invoke-ShopkeeperCompose ps
    Invoke-ShopkeeperCompose logs --tail 100 api embedding
    throw
}

if (-not $SkipKnowledgeBuild) {
    & (Join-Path $PSScriptRoot "build_knowledge.ps1")
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

& (Join-Path $PSScriptRoot "smoke_full_stack.ps1")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$frontendPort = Get-DotEnvInt -Name "FRONTEND_HOST_PORT" -Default 5173
Write-Host "Shopkeeper Agent is ready: http://127.0.0.1:$frontendPort" -ForegroundColor Green
