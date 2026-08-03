$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot ".env"

function Get-ServicePort {
    param(
        [string]$Name,
        [int]$Default
    )

    if (Test-Path $envFile) {
        $entry = Get-Content $envFile |
            Where-Object { $_ -match "^$([regex]::Escape($Name))=" } |
            Select-Object -First 1
        if ($entry) {
            return [int](($entry -split "=", 2)[1].Trim().Trim('"').Trim("'"))
        }
    }

    return $Default
}

$mysqlPort = Get-ServicePort -Name "MYSQL_HOST_PORT" -Default 3307
$qdrantPort = Get-ServicePort -Name "QDRANT_HTTP_HOST_PORT" -Default 6335
$elasticsearchPort = Get-ServicePort -Name "ELASTICSEARCH_HOST_PORT" -Default 9201
$kibanaPort = Get-ServicePort -Name "KIBANA_HOST_PORT" -Default 5602
$embeddingPort = Get-ServicePort -Name "EMBEDDING_HOST_PORT" -Default 8082

function Test-HttpService {
    param(
        [string]$Name,
        [string]$Uri
    )

    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 10
        if ($response.StatusCode -eq 200) {
            Write-Host "[OK] $Name -> $Uri" -ForegroundColor Green
            return $true
        }
    }
    catch {
        Write-Host "[FAIL] $Name -> $Uri ($($_.Exception.Message))" -ForegroundColor Red
    }

    return $false
}

$results = @()

$mysql = Test-NetConnection -ComputerName localhost -Port $mysqlPort -WarningAction SilentlyContinue
if ($mysql.TcpTestSucceeded) {
    Write-Host "[OK] MySQL -> localhost:$mysqlPort" -ForegroundColor Green
    $results += $true
}
else {
    Write-Host "[FAIL] MySQL -> localhost:$mysqlPort" -ForegroundColor Red
    $results += $false
}

$results += Test-HttpService -Name "Qdrant" -Uri "http://localhost:$qdrantPort/collections"
$results += Test-HttpService -Name "Elasticsearch" -Uri "http://localhost:$elasticsearchPort/_cluster/health"
$results += Test-HttpService -Name "Kibana" -Uri "http://localhost:$kibanaPort/api/status"
$results += Test-HttpService -Name "Embedding" -Uri "http://localhost:$embeddingPort/health"

if ($results -contains $false) {
    Write-Host "One or more required services are unavailable." -ForegroundColor Red
    exit 1
}

$body = @{ inputs = "销售额" } | ConvertTo-Json
$embedding = Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:$embeddingPort/embed" `
    -ContentType "application/json" `
    -Body $body

if ($embedding[0].Count -ne 1024) {
    Write-Host "[FAIL] Embedding dimension is $($embedding[0].Count), expected 1024." -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Embedding dimension -> 1024" -ForegroundColor Green
Write-Host "All Shopkeeper rebuild services are ready." -ForegroundColor Green
