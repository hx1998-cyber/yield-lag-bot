# Windows Automation Scripts

These scripts run local public-market data collection, hourly archival, database backup,
and health checks for the Windows workstation. They do not enable live trading, do not use
Hyperliquid private APIs, and do not place orders.

Default data root:

```powershell
E:\QuantData\yield-lag
```

If `YIELD_LAG_DATA_ROOT` is already set in your environment, the scripts use that value
instead. Run all commands from PowerShell.

## Manual Commands

Start the long-running public Hyperliquid BBO collector:

```powershell
E:\QuantProjects\yield-lag-bot\scripts\windows\start_collector.ps1
```

Archive the previous complete UTC hour:

```powershell
E:\QuantProjects\yield-lag-bot\scripts\windows\archive_last_hour.ps1
```

Back up the local Postgres database:

```powershell
E:\QuantProjects\yield-lag-bot\scripts\windows\backup_db.ps1
```

Check local data health, recent BBO rows, manifest rows, and backup files:

```powershell
E:\QuantProjects\yield-lag-bot\scripts\windows\check_data_health.ps1
```

If your PowerShell execution policy blocks local scripts, run a command with:

```powershell
powershell.exe -ExecutionPolicy Bypass -File E:\QuantProjects\yield-lag-bot\scripts\windows\check_data_health.ps1
```

## Keep The Collector Running

`start_collector.ps1` starts `postgres` and `redis`, activates `.venv`, and loops forever.
Each one-hour collection run writes a log under:

```powershell
E:\QuantData\yield-lag\logs\collector
```

Practical options:

- Run it in a dedicated PowerShell window and leave that window open.
- Use Windows Terminal with a dedicated tab.
- Use Task Scheduler with trigger "At startup" and action:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File E:\QuantProjects\yield-lag-bot\scripts\windows\start_collector.ps1
```

## Hourly Archive Task

Windows Task Scheduler should run scheduled work. Codex can write and maintain these
scripts, but Task Scheduler owns the hourly/daily execution on this machine.

Suggested hourly archive setup:

1. Open Task Scheduler.
2. Choose "Create Task...".
3. Name it `YIELD-LAG archive previous UTC hour`.
4. On "Triggers", add a new trigger:
   - Begin the task: `On a schedule`
   - Settings: `Daily`
   - Start: choose a time a few minutes after the next hour, for example `00:05`
   - Repeat task every: `1 hour`
   - For a duration of: `Indefinitely`
5. On "Actions", add:
   - Program/script: `powershell.exe`
   - Add arguments:

```text
-NoProfile -ExecutionPolicy Bypass -File E:\QuantProjects\yield-lag-bot\scripts\windows\archive_last_hour.ps1
```

6. On "Settings", enable "Run task as soon as possible after a scheduled start is missed".

Archive logs are written under:

```powershell
E:\QuantData\yield-lag\logs\exporter
```

## Daily Database Backup Task

Suggested daily backup setup:

1. Open Task Scheduler.
2. Choose "Create Task...".
3. Name it `YIELD-LAG daily Postgres backup`.
4. On "Triggers", add a daily trigger at a quiet time, for example `00:15`.
5. On "Actions", add:
   - Program/script: `powershell.exe`
   - Add arguments:

```text
-NoProfile -ExecutionPolicy Bypass -File E:\QuantProjects\yield-lag-bot\scripts\windows\backup_db.ps1
```

Backups are written under:

```powershell
E:\QuantData\yield-lag\db_backups
```

## Notes

- Docker compose file: `E:\QuantProjects\yield-lag-bot\docker\docker-compose.yml`
- Required services: `postgres`, `redis`
- The scripts force `YIELD_LAG_LIVE_TRADING=false` where Python collection/export code runs.
- No secrets are stored in these scripts.
- No CME live stream is started by these scripts.
