Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ComposeFile = Join-Path $ProjectRoot "docker\docker-compose.yml"

Set-Location $ProjectRoot

if ([string]::IsNullOrWhiteSpace($env:YIELD_LAG_DATA_ROOT)) {
    $env:YIELD_LAG_DATA_ROOT = "E:\QuantData\yield-lag"
}

$DataRoot = $env:YIELD_LAG_DATA_ROOT
$PostgresUser = if ([string]::IsNullOrWhiteSpace($env:POSTGRES_USER)) { "yield_lag" } else { $env:POSTGRES_USER }
$PostgresDb = if ([string]::IsNullOrWhiteSpace($env:POSTGRES_DB)) { "yield_lag" } else { $env:POSTGRES_DB }

function Invoke-Psql {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Sql
    )

    & docker compose --project-directory $ProjectRoot -f $ComposeFile exec -T postgres `
        psql -U $PostgresUser -d $PostgresDb -v ON_ERROR_STOP=1 -c $Sql
}

Write-Host ""
Write-Host "=== market_ticks by venue/symbol/channel ==="
Invoke-Psql @"
SELECT
    venue,
    symbol,
    COALESCE(raw_payload->>'channel', '(missing)') AS channel,
    COUNT(*) AS rows,
    MIN(exchange_ts) AS min_exchange_ts,
    MAX(exchange_ts) AS max_exchange_ts,
    MAX(receive_ts) AS max_receive_ts
FROM market_ticks
GROUP BY venue, symbol, COALESCE(raw_payload->>'channel', '(missing)')
ORDER BY venue, symbol, channel;
"@

Write-Host ""
Write-Host "=== latest 10 BBO rows ==="
Invoke-Psql @"
SELECT
    receive_ts,
    exchange_ts,
    venue,
    symbol,
    bid_price,
    ask_price,
    bid_size,
    ask_size,
    raw_payload->>'channel' AS channel
FROM market_ticks
WHERE raw_payload->>'channel' = 'bbo'
ORDER BY receive_ts DESC
LIMIT 10;
"@

Write-Host ""
Write-Host "=== last 10 manifest rows ==="
$ManifestPath = Join-Path $DataRoot "manifests\hyperliquid_bbo_manifest.csv"
if (Test-Path $ManifestPath) {
    Import-Csv -LiteralPath $ManifestPath |
        Select-Object -Last 10 |
        Format-Table -AutoSize
} else {
    Write-Host "Manifest not found: $ManifestPath"
}

Write-Host ""
Write-Host "=== latest database backups ==="
$BackupDir = Join-Path $DataRoot "db_backups"
if (Test-Path $BackupDir) {
    $Backups = Get-ChildItem -LiteralPath $BackupDir -Filter "*.sql" |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 10 FullName, Length, LastWriteTimeUtc
    if ($Backups) {
        $Backups | Format-Table -AutoSize
    } else {
        Write-Host "No .sql backups found in $BackupDir"
    }
} else {
    Write-Host "Backup directory not found: $BackupDir"
}
