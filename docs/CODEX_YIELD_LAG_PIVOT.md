# Codex Task: Pivot baccarat into Project YIELD-LAG

## Background

The existing repository `hx1998-cyber/baccarat` was originally created as a Polymarket automated trading bot for copy-trading and merge-redeem arbitrage on Polygon.

We are changing the trading direction completely while keeping the engineering skeleton.

New direction:

> Research high-frequency time / lead-lag opportunities between CME U.S. Treasury futures and crypto perpetual futures.

This is not risk-free arbitrage. Treat it as cross-market lead-lag statistical research first. Real trading must stay disabled until research and paper trading prove positive expectancy after fees, spread, slippage, and latency.

## Repository strategy

Preferred new repository name:

`yield-lag-bot`

If creating a new GitHub repository manually, use this flow:

```bash
git clone https://github.com/hx1998-cyber/baccarat.git yield-lag-bot
cd yield-lag-bot
rm -rf .git
git init
git branch -M main
git add .
git commit -m "chore: initialize yield lag bot from baccarat skeleton"
gh repo create hx1998-cyber/yield-lag-bot --public --source=. --remote=origin --push
```

If working directly inside the existing `baccarat` repo, create a branch instead:

```bash
git checkout -b feat/yield-lag-pivot
```

Do not touch real trading credentials. Do not enable live trading.

## Product definition

Project name:

`Project YIELD-LAG`

Core idea:

Use CME Treasury futures as a macro/interest-rate shock signal source and crypto perpetual futures as the execution/research target.

Initial CME signal symbols:

- `ZT` - 2-Year T-Note Futures
- `ZF` - 5-Year T-Note Futures
- `ZN` - 10-Year T-Note Futures
- `TN` - Ultra 10-Year T-Note Futures
- optionally later: `ZB`, `UB`

Initial crypto target symbols:

- `BTCUSDT`
- `ETHUSDT`

Supported crypto venues for M1:

- Binance USD-M Futures public market data
- Bybit v5 public market data
- OKX can remain a stub for now

CME data for M1:

- Implement CME adapter as a stub.
- Implement Databento / GLBX.MDP3 historical adapter as a stub interface only.
- Do not hardcode paid credentials.

## What to preserve from the old project

Keep the following structure where possible:

- Docker / docker-compose skeleton
- Postgres / Redis services
- app entrypoint pattern
- dry-run / paper-only safety pattern
- config module
- logging pattern
- dashboard or monitoring skeleton if present
- tests framework
- documentation structure

Remove or deprecate Polymarket-specific concepts:

- Polymarket CLOB scanner
- Polygon transaction execution
- merge / redeem logic
- yes/no market assumptions
- copy-trading wallet logic
- Polymarket-specific environment variables

## M1 objective

Build only a research-grade data and latency collection platform.

Do not implement real order placement in M1.

M1 must deliver:

1. Normalized market event model
2. Crypto public WebSocket adapters
3. CME / Databento adapter stubs
4. SQL schema for market ticks, latency stats, signals, and paper orders
5. Latency monitor
6. Lead-lag research module skeleton
7. Tests
8. README rewrite
9. Safety flags with live trading disabled by default

## Required normalized market event model

Create a Python dataclass or Pydantic model named `MarketEvent` with at least:

```python
venue: str
symbol: str
instrument_type: str
exchange_ts: datetime | None
receive_ts: datetime
process_ts: datetime | None
bid_price: Decimal | None
ask_price: Decimal | None
bid_size: Decimal | None
ask_size: Decimal | None
last_price: Decimal | None
sequence_id: str | int | None
raw_payload: dict
```

Recommended path:

`src/yield_lag_bot/models/market_event.py`

If the existing project has a package name, either rename it carefully or keep compatibility wrappers.

## Required SQL tables

Add or update `sql/init.sql` with:

```sql
CREATE TABLE IF NOT EXISTS market_ticks (
    id BIGSERIAL PRIMARY KEY,
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    instrument_type TEXT NOT NULL,
    exchange_ts TIMESTAMPTZ NULL,
    receive_ts TIMESTAMPTZ NOT NULL,
    process_ts TIMESTAMPTZ NULL,
    bid_price NUMERIC NULL,
    ask_price NUMERIC NULL,
    bid_size NUMERIC NULL,
    ask_size NUMERIC NULL,
    last_price NUMERIC NULL,
    sequence_id TEXT NULL,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_market_ticks_symbol_time
    ON market_ticks(symbol, receive_ts DESC);

CREATE INDEX IF NOT EXISTS idx_market_ticks_venue_symbol_time
    ON market_ticks(venue, symbol, receive_ts DESC);

CREATE TABLE IF NOT EXISTS latency_stats (
    id BIGSERIAL PRIMARY KEY,
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange_ts TIMESTAMPTZ NULL,
    receive_ts TIMESTAMPTZ NOT NULL,
    process_ts TIMESTAMPTZ NULL,
    receive_delay_ms NUMERIC NULL,
    process_delay_ms NUMERIC NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS signals (
    id BIGSERIAL PRIMARY KEY,
    signal_name TEXT NOT NULL,
    cme_symbol TEXT NOT NULL,
    crypto_symbol TEXT NOT NULL,
    window_ms INTEGER NOT NULL,
    horizon_ms INTEGER NOT NULL,
    signal_value NUMERIC NOT NULL,
    predicted_side TEXT NULL,
    confidence NUMERIC NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS paper_orders (
    id BIGSERIAL PRIMARY KEY,
    signal_id BIGINT NULL REFERENCES signals(id),
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    price NUMERIC NOT NULL,
    qty NUMERIC NOT NULL,
    fee NUMERIC NOT NULL DEFAULT 0,
    slippage NUMERIC NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'simulated',
    pnl NUMERIC NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Required module layout

Target structure:

```text
src/yield_lag_bot/
  config.py
  models/
    market_event.py
  data/
    normalizer.py
    recorder.py
    binance_futures_adapter.py
    bybit_adapter.py
    okx_adapter.py
    cme_adapter.py
    databento_adapter.py
  research/
    lead_lag_analyzer.py
    latency_report.py
    event_study.py
    fee_slippage_model.py
  strategy/
    treasury_shock_signal.py
    curve_signal.py
    macro_event_signal.py
    signal_router.py
  execution/
    paper_executor.py
    crypto_executor_stub.py
    cme_executor_stub.py
  risk/
    risk_manager.py
    kill_switch.py
    stale_data_guard.py
  jobs/
    collect_market_data.py
    run_research.py
    run_paper_trading.py
  dashboard/
    app.py
```

If the current repo already has a different folder structure, adapt while keeping the same functional boundaries.

## Adapter requirements

### Binance futures adapter

Use public market data only.

Must support:

- best bid / ask stream or book ticker stream
- trade stream optional
- reconnect loop
- heartbeat / stale data detection
- convert payload into `MarketEvent`

### Bybit adapter

Use public v5 WebSocket only.

Must support:

- orderbook stream for BTCUSDT and ETHUSDT
- parse venue timestamp fields when available
- convert payload into `MarketEvent`

### CME adapter

M1 only:

- create interface/stub
- no real CME credentials
- no real CME order placement
- allow loading historical CSV/parquet later

### Databento adapter

M1 only:

- create interface/stub
- no paid API key hardcoding
- method placeholders for historical GLBX.MDP3 loading

## Research module requirements

Create `lead_lag_analyzer.py` that can:

- accept normalized tick dataframe
- compute mid price
- resample or align by receive timestamp
- compute returns over windows:
  - 100ms
  - 250ms
  - 500ms
  - 1s
  - 3s
  - 5s
- compare CME signal returns against future crypto target returns
- output CSV report with:
  - cme_symbol
  - crypto_symbol
  - window_ms
  - horizon_ms
  - sample_count
  - correlation
  - hit_rate
  - average_forward_return_bps
  - estimated_fee_bps
  - estimated_slippage_bps
  - net_forward_return_bps

Important:

Do not assume direction such as `ZN up => BTC up`. Let the analysis report reveal the empirical relationship.

## Risk and safety requirements

Default settings must be safe:

```env
LIVE_TRADING=false
PAPER_TRADING=true
MAX_ORDER_USD=10
MAX_POSITION_USD=50
MAX_DAILY_LOSS_USD=20
MAX_LATENCY_MS=300
STALE_DATA_MS=500
KILL_SWITCH_ON_ERROR=true
```

Real order placement must be disabled in M1.

If any execution code exists, it must raise a clear exception when `LIVE_TRADING=false` or when credentials are missing.

## Tests required

Add tests for:

1. normalizer converts Binance payload to `MarketEvent`
2. normalizer converts Bybit payload to `MarketEvent`
3. latency calculation works when `exchange_ts` and `receive_ts` are present
4. stale data guard rejects old events
5. lead-lag analyzer aligns windows correctly
6. M1 cannot place live orders

## README rewrite

Rewrite README around this positioning:

- Project YIELD-LAG
- CME Treasury futures × crypto perpetual lead-lag research
- Not risk-free arbitrage
- M1 is data collection and research only
- No live trading by default
- How to run Docker
- How to run tests
- How to run data collection
- How to run a research report

## Acceptance criteria

M1 is complete when:

```bash
pytest
```

passes, and:

```bash
docker compose up --build
```

starts Postgres / Redis / app without enabling live trading.

The app should be able to collect public crypto market data and write normalized ticks to the database.

## Hard prohibitions

- Do not enable live trading.
- Do not add real API keys.
- Do not claim this is risk-free arbitrage.
- Do not add CME live order execution.
- Do not add paid market data assumptions as mandatory for local development.
- Do not rewrite the entire project from scratch if existing skeleton can be reused.
