Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ComposeFile = Join-Path $ProjectRoot "docker\docker-compose.yml"
$ActivateScript = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"

Set-Location $ProjectRoot

if ([string]::IsNullOrWhiteSpace($env:YIELD_LAG_DATA_ROOT)) {
    $env:YIELD_LAG_DATA_ROOT = "E:\QuantData\yield-lag"
}
$env:YIELD_LAG_LIVE_TRADING = "false"

$DataRoot = $env:YIELD_LAG_DATA_ROOT
$CollectorLogDir = Join-Path $DataRoot "logs\collector"
$RuntimeDir = Join-Path $DataRoot "runtime"
$CollectorLockPath = Join-Path $RuntimeDir "collector.lock"
$RequiredDirs = @(
    $DataRoot,
    $RuntimeDir,
    (Join-Path $DataRoot "logs"),
    $CollectorLogDir,
    (Join-Path $DataRoot "hyperliquid\bbo\hourly"),
    (Join-Path $DataRoot "manifests")
)
$RequiredDirs | ForEach-Object { New-Item -ItemType Directory -Force -Path $_ | Out-Null }

function Get-CollectorLock {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    } catch {
        Write-Host "Existing collector lock is unreadable; treating it as stale: $Path"
        return $null
    }
}

function Test-ProcessRunning {
    param(
        [Parameter(Mandatory = $true)]
        [int] $ProcessId
    )

    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function New-CollectorLock {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot
    )

    $Lock = [ordered]@{
        process_id = $PID
        started_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        project_root = $ProjectRoot
    }
    $LockJson = $Lock | ConvertTo-Json
    $Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    $FileStream = $null
    $Writer = $null

    try {
        $FileStream = [System.IO.File]::Open(
            $Path,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        $Writer = [System.IO.StreamWriter]::new($FileStream, $Utf8NoBom)
        $Writer.WriteLine($LockJson)
    } finally {
        if ($null -ne $Writer) {
            $Writer.Dispose()
        } elseif ($null -ne $FileStream) {
            $FileStream.Dispose()
        }
    }
}

function Remove-OwnCollectorLock {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    $Lock = Get-CollectorLock -Path $Path
    if ($null -ne $Lock -and $Lock.process_id -eq $PID) {
        Remove-Item -LiteralPath $Path -Force
    }
}

if (Test-Path -LiteralPath $CollectorLockPath) {
    $ExistingLock = Get-CollectorLock -Path $CollectorLockPath
    $ExistingPid = if ($null -ne $ExistingLock -and $ExistingLock.PSObject.Properties.Name -contains "process_id") {
        [int] $ExistingLock.process_id
    } else {
        $null
    }

    if ($null -ne $ExistingPid -and (Test-ProcessRunning -ProcessId $ExistingPid)) {
        Write-Host "Collector already appears to be running with process id $ExistingPid."
        Write-Host "Lock file: $CollectorLockPath"
        exit 0
    }

    Write-Host "Removing stale collector lock: $CollectorLockPath"
    Remove-Item -LiteralPath $CollectorLockPath -Force
}

try {
    New-CollectorLock -Path $CollectorLockPath -ProjectRoot $ProjectRoot
} catch [System.IO.IOException] {
    $ExistingLock = Get-CollectorLock -Path $CollectorLockPath
    $ExistingPid = if ($null -ne $ExistingLock -and $ExistingLock.PSObject.Properties.Name -contains "process_id") {
        [int] $ExistingLock.process_id
    } else {
        $null
    }
    if ($null -ne $ExistingPid -and (Test-ProcessRunning -ProcessId $ExistingPid)) {
        Write-Host "Collector already appears to be running with process id $ExistingPid."
        Write-Host "Lock file: $CollectorLockPath"
        exit 0
    }
    throw
}

if (-not (Test-Path $ActivateScript)) {
    throw "Virtual environment activation script not found: $ActivateScript"
}

try {
    . $ActivateScript

    Write-Host "Project root: $ProjectRoot"
    Write-Host "Data root: $DataRoot"
    Write-Host "Collector lock: $CollectorLockPath"
    Write-Host "Starting postgres and redis..."
    & docker compose --project-directory $ProjectRoot -f $ComposeFile up -d postgres redis
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up failed with exit code $LASTEXITCODE"
    }

    while ($true) {
        $Timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmssZ")
        $LogPath = Join-Path $CollectorLogDir "hyperliquid_bbo_$Timestamp.log"
        $StartedAt = (Get-Date).ToUniversalTime().ToString("o")

        "[$StartedAt] Starting Hyperliquid public BBO collection for BTC,ETH" |
            Tee-Object -FilePath $LogPath

        try {
            & python -m yield_lag_bot.jobs.collect_market_data `
                --venue hyperliquid `
                --symbols BTC,ETH `
                --duration 3600 *>&1 |
                Tee-Object -FilePath $LogPath -Append

            $ExitCode = $LASTEXITCODE
            $FinishedAt = (Get-Date).ToUniversalTime().ToString("o")
            if ($ExitCode -eq 0) {
                "[$FinishedAt] Collector run completed successfully" |
                    Tee-Object -FilePath $LogPath -Append
            } else {
                "[$FinishedAt] Collector run failed with exit code $ExitCode; continuing after sleep" |
                    Tee-Object -FilePath $LogPath -Append
            }
        } catch {
            $ErroredAt = (Get-Date).ToUniversalTime().ToString("o")
            "[$ErroredAt] Collector run threw an exception: $($_.Exception.Message)" |
                Tee-Object -FilePath $LogPath -Append
        }

        Start-Sleep -Seconds 10
    }
} finally {
    Remove-OwnCollectorLock -Path $CollectorLockPath
}
