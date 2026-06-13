Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ActivateScript = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"

Set-Location $ProjectRoot

if ([string]::IsNullOrWhiteSpace($env:YIELD_LAG_DATA_ROOT)) {
    $env:YIELD_LAG_DATA_ROOT = "E:\QuantData\yield-lag"
}
$env:YIELD_LAG_LIVE_TRADING = "false"

$DataRoot = $env:YIELD_LAG_DATA_ROOT
$ExporterLogDir = Join-Path $DataRoot "logs\exporter"
$RequiredDirs = @(
    $DataRoot,
    (Join-Path $DataRoot "logs"),
    $ExporterLogDir,
    (Join-Path $DataRoot "hyperliquid\bbo\hourly"),
    (Join-Path $DataRoot "manifests")
)
$RequiredDirs | ForEach-Object { New-Item -ItemType Directory -Force -Path $_ | Out-Null }

if (-not (Test-Path $ActivateScript)) {
    throw "Virtual environment activation script not found: $ActivateScript"
}
. $ActivateScript

$CurrentHourUtc = (Get-Date).ToUniversalTime()
$CurrentHourUtc = [DateTime]::SpecifyKind(
    [DateTime]::new(
        $CurrentHourUtc.Year,
        $CurrentHourUtc.Month,
        $CurrentHourUtc.Day,
        $CurrentHourUtc.Hour,
        0,
        0
    ),
    [DateTimeKind]::Utc
)
$PreviousHourUtc = $CurrentHourUtc.AddHours(-1)

$StartIso = $PreviousHourUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")
$EndIso = $CurrentHourUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")
$StartToken = $PreviousHourUtc.ToString("yyyyMMdd_HHmmssZ")
$EndToken = $CurrentHourUtc.ToString("yyyyMMdd_HHmmssZ")
$LogPath = Join-Path $ExporterLogDir "archive_${StartToken}_${EndToken}.log"

"[$((Get-Date).ToUniversalTime().ToString("o"))] Archiving Hyperliquid BBO from $StartIso to $EndIso" |
    Tee-Object -FilePath $LogPath

try {
    & python -m yield_lag_bot.jobs.archive_hyperliquid_bbo `
        --symbols BTC,ETH `
        --start $StartIso `
        --end $EndIso *>&1 |
        Tee-Object -FilePath $LogPath -Append

    if ($LASTEXITCODE -ne 0) {
        throw "archive_hyperliquid_bbo failed with exit code $LASTEXITCODE"
    }
} catch {
    "[$((Get-Date).ToUniversalTime().ToString("o"))] Archive failed: $($_.Exception.Message)" |
        Tee-Object -FilePath $LogPath -Append
    throw
}

"[$((Get-Date).ToUniversalTime().ToString("o"))] Archive finished; log: $LogPath" |
    Tee-Object -FilePath $LogPath -Append
