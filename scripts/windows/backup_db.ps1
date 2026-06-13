Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ComposeFile = Join-Path $ProjectRoot "docker\docker-compose.yml"

Set-Location $ProjectRoot

if ([string]::IsNullOrWhiteSpace($env:YIELD_LAG_DATA_ROOT)) {
    $env:YIELD_LAG_DATA_ROOT = "E:\QuantData\yield-lag"
}

$DataRoot = $env:YIELD_LAG_DATA_ROOT
$BackupDir = Join-Path $DataRoot "db_backups"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$PostgresUser = if ([string]::IsNullOrWhiteSpace($env:POSTGRES_USER)) { "yield_lag" } else { $env:POSTGRES_USER }
$PostgresDb = if ([string]::IsNullOrWhiteSpace($env:POSTGRES_DB)) { "yield_lag" } else { $env:POSTGRES_DB }
$Timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmssZ")
$BackupPath = Join-Path $BackupDir "yield_lag_$Timestamp.sql"

Write-Host "Writing Postgres backup to $BackupPath"
& docker compose --project-directory $ProjectRoot -f $ComposeFile exec -T postgres `
    pg_dump -U $PostgresUser -d $PostgresDb |
    Out-File -FilePath $BackupPath -Encoding utf8

if ($LASTEXITCODE -ne 0) {
    if (Test-Path $BackupPath) {
        Remove-Item -LiteralPath $BackupPath -Force
    }
    throw "pg_dump failed with exit code $LASTEXITCODE"
}

$BackupItem = Get-Item -LiteralPath $BackupPath
Write-Host "Backup path: $($BackupItem.FullName)"
Write-Host "Backup size: $($BackupItem.Length) bytes"
