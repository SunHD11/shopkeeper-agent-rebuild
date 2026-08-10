$ErrorActionPreference = "Stop"

$script:ProjectRoot = Split-Path -Parent $PSScriptRoot
$script:EnvFile = Join-Path $script:ProjectRoot ".env"
$script:ComposeFile = Join-Path $script:ProjectRoot "docker\docker-compose.yaml"

function Get-DotEnvValues {
    $values = @{}
    if (-not (Test-Path $script:EnvFile)) {
        return $values
    }

    foreach ($line in Get-Content $script:EnvFile) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }

        $name, $value = $trimmed -split "=", 2
        $values[$name.Trim()] = $value.Trim().Trim('"').Trim("'")
    }
    return $values
}

function Get-DotEnvInt {
    param(
        [Parameter(Mandatory)]
        [string]$Name,
        [Parameter(Mandatory)]
        [int]$Default
    )

    # Process-level overrides allow parallel projects without editing .env.
    $processValue = [Environment]::GetEnvironmentVariable($Name)
    if ($processValue) {
        return [int]$processValue
    }

    $values = Get-DotEnvValues
    if ($values.ContainsKey($Name)) {
        return [int]$values[$Name]
    }
    return $Default
}

function Invoke-ShopkeeperCompose {
    param(
        [Parameter(ValueFromRemainingArguments)]
        [string[]]$Arguments
    )

    & docker compose --env-file $script:EnvFile -f $script:ComposeFile @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed with exit code $LASTEXITCODE"
    }
}

function Wait-HttpReady {
    param(
        [Parameter(Mandatory)]
        [string]$Name,
        [Parameter(Mandatory)]
        [string]$Uri,
        [Parameter(Mandatory)]
        [datetime]$Deadline
    )

    $attempt = 0
    while ((Get-Date) -lt $Deadline) {
        $attempt += 1
        try {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 12
            if ($response.StatusCode -eq 200) {
                Write-Host "[OK] $Name -> $Uri" -ForegroundColor Green
                return
            }
        }
        catch {
            if ($attempt % 6 -eq 0) {
                Write-Host "[WAIT] $Name is still preparing ($($_.Exception.Message))" -ForegroundColor Yellow
            }
        }
        Start-Sleep -Seconds 5
    }

    throw "$Name did not become ready before timeout: $Uri"
}
