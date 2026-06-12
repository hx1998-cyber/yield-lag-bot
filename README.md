# Project YIELD-LAG

Project YIELD-LAG is a research system for studying lead-lag relationships between CME U.S. Treasury futures and crypto perpetual futures.

The initial hypothesis space is macro and rates shocks from Treasury futures (`ZT`, `ZF`, `ZN`, `TN`) against liquid crypto perpetuals (`BTCUSDT`, `ETHUSDT`). This is not risk-free arbitrage. M1 is data collection, latency measurement, and research plumbing only.

## M1 Scope

- Normalized `MarketEvent` model.
- Binance USD-M Futures public WebSocket adapter.
- Bybit v5 public WebSocket adapter.
- Hyperliquid public WebSocket adapter for trades and BBO.
- CME and Databento historical adapter stubs.
- Postgres schema for `market_ticks`, `latency_stats`, `signals`, and `paper_orders`.
- Latency calculation and stale data guard.
- Lead-lag analyzer for aligned window and forward-return reports.
- Paper-only execution boundary. `LIVE_TRADING=false` by default.

No live order placement, real API keys, CME execution, or paid-data assumptions are included in M1.

## Layout

```text
src/yield_lag_bot/
  models/       normalized event model
  data/         public adapters, normalizer, recorder, CME/Databento stubs
  research/     latency and lead-lag analysis
  strategy/     M2 signal skeletons
  execution/    paper executor and live executor stubs
  risk/         stale data guard and safety shells
  jobs/         collection and research entrypoints
  dashboard/    monitoring placeholder
```

The legacy `src/baccarat` package is kept as compatibility skeleton for the existing Docker/Postgres/Redis/Python structure while Project YIELD-LAG modules live under `src/yield_lag_bot`.

## Safety Defaults

```env
YIELD_LAG_LIVE_TRADING=false
YIELD_LAG_PAPER_TRADING=true
YIELD_LAG_MAX_ORDER_USD=10
YIELD_LAG_MAX_POSITION_USD=50
YIELD_LAG_MAX_DAILY_LOSS_USD=20
YIELD_LAG_MAX_LATENCY_MS=300
YIELD_LAG_STALE_DATA_MS=500
YIELD_LAG_KILL_SWITCH_ON_ERROR=true
```

## Run Locally

Install development dependencies:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

Start Postgres, Redis, and the M1 app:

```bash
docker compose -f docker/docker-compose.yml up --build
```

Run migrations after services are up:

```bash
alembic upgrade head
```

Collect public Binance book-ticker events:

```bash
python -m yield_lag_bot.jobs.collect_market_data
```

Collect 10 minutes of Hyperliquid public trades and BBO:

```bash
python -m yield_lag_bot.jobs.collect_market_data --venue hyperliquid --symbols BTC,ETH --duration 600
```

Export Hyperliquid ticks:

```bash
python -m yield_lag_bot.jobs.export_ticks --venue hyperliquid --symbols BTC,ETH --out ticks.csv
```

Export BBO-only Hyperliquid ticks for price research:

```bash
python -m yield_lag_bot.jobs.export_ticks --venue hyperliquid --symbols BTC,ETH --channel bbo --out ticks_bbo.csv
```

## M3B Databento Historical CME Import

Install the optional Databento dependency and set the historical data API key from the environment:

```bash
pip install -e ".[dev,databento]"
$env:DATABENTO_API_KEY="your-databento-api-key"
```

Download a 1-hour CME GLBX.MDP3 MBP-1 sample into the M3A-compatible CME CSV format:

```bash
python -m yield_lag_bot.jobs.download_cme_databento --dataset GLBX.MDP3 --schema mbp-1 --symbols ZN.c.0 --start 2026-06-12T13:00:00Z --end 2026-06-12T14:00:00Z --out cme_ticks.csv
```

The output columns are `timestamp,symbol,bid_price,ask_price,last_price`. Symbols are sent to Databento exactly as provided. `ZN.c.0`, `ZF.c.0`, `ZT.c.0`, and `TN.c.0` are intended examples, but availability depends on your Databento symbology access.

Run the M3A lead-lag study using the downloaded CME CSV and a Hyperliquid BBO export:

```bash
python -m yield_lag_bot.jobs.run_lead_lag_study --cme-csv cme_ticks.csv --crypto-csv ticks_bbo.csv --out lead_lag_study.csv --cme-symbol ZN.c.0 --crypto-symbol BTC
```

This is historical research only. There is no CME live stream, Hyperliquid private API, or order placement in M3B. Keep `YIELD_LAG_LIVE_TRADING=false`.

## M3C Experiment Runner

Run a repeatable CME Treasury futures vs Hyperliquid BBO lead-lag experiment from YAML:

```bash
python -m yield_lag_bot.jobs.run_experiment --config examples/experiments/macro_windows.example.yaml
```

The example uses local sample CSVs and writes:

```text
examples/experiment_outputs/macro_windows_example/sample_window/ZN__BTC__lead_lag.csv
examples/experiment_outputs/macro_windows_example/summary.csv
```

To plug in real files, edit the window in `examples/experiments/macro_windows.example.yaml`:

```yaml
cme_csv: "path/to/cme_ticks.csv"
crypto_csv: "path/to/ticks_bbo.csv"
```

`cme_ticks.csv` should use the M3A/M3B columns `timestamp,symbol,bid_price,ask_price,last_price`. `ticks_bbo.csv` should be a Hyperliquid BBO export with `symbol`, `receive_ts`, and either `mid_price` or `bid_price` plus `ask_price`.

M3C is research orchestration only. It does not download Databento data, connect to a CME live stream, call Hyperliquid private APIs, or place orders. Keep `YIELD_LAG_LIVE_TRADING=false`.

Run a research report from a CSV of normalized ticks:

```bash
python -m yield_lag_bot.jobs.run_research ticks.csv lead_lag_report.csv --cme-symbol ZN --crypto-symbol BTCUSDT
```

Replay saved ticks through the analyzer path:

```bash
python -m yield_lag_bot.jobs.replay_market_data ticks.csv --out lead_lag_report.csv --cme-symbol ZN --crypto-symbol BTC
```

The CSV must include `symbol`, `receive_ts`, and either `mid_price` or `bid_price` plus `ask_price`.
For lead-lag price studies, prefer BBO-derived `mid_price` data. Trades-only replay can verify the pipeline, but it is only a smoke test because trade prints are noisier than BBO/mid-price observations.

## Remaining M2 Work

- Persist live public WebSocket events continuously into Postgres.
- Build richer event studies around scheduled macro releases and rates shocks.
- Add signal generation, paper trading loop, fee/slippage calibration, and dashboard views.
- Expand operational monitoring for stale streams, reconnects, and latency alerts.

## License

Proprietary, internal use only.
