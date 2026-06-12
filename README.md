# baccarat

Polymarket automated trading bot — **copy-trading** & **merge-redeem arbitrage** on Polygon.

> Single-instance, fully-async (`asyncio`) Python bot. Postgres is the source of
> truth, Redis is the performance view, all inter-module communication uses
> `asyncio.Queue`. Designed to be easy to operate and easy to debug — every
> signal carries a `trace_id` that propagates across logs from ingestion to
> on-chain settlement.

## Status

**M1 — Architecture Initialization (current).**
This milestone delivers project skeleton, infra, DB schema, base classes,
config & logging. Business logic lands in M2 onward. See `docs/` (TBD) for
milestone definitions.

## Project layout

```
src/baccarat/
├── core/         # config, logger, exceptions, common dataclasses, trace_id
├── ingestion/    # market data (Polymarket WS) + chain listener (Polygon RPC)
├── strategy/     # CopyTrade + Arbitrage (Maker-Taker state machine)
├── execution/    # wallet, gas, tx builder/submitter, position manager
├── risk/         # hard-limit risk manager (size / drawdown / rate)
├── monitoring/   # Telegram alerts + metrics
├── storage/      # SQLAlchemy models + Postgres + Redis clients
└── app.py        # asyncio orchestrator — wires queues + tasks
```

## Quick start (development)

Requires Docker, Docker Compose and Python 3.11+.

```bash
# 1. Copy templates and fill in secrets
cp config/settings.example.yaml config/settings.yaml
cp .env.example .env
# Edit .env: PRIVATE_KEY, RPC_URLS, TELEGRAM_BOT_TOKEN, POSTGRES_PASSWORD

# 2. Bring up infra + bot
docker compose -f docker/docker-compose.yml up --build

# 3. Run DB migrations (one-shot)
docker compose -f docker/docker-compose.yml run --rm bot alembic upgrade head
```

For local dev without containers:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# Bring up only redis + postgres in Docker:
docker compose -f docker/docker-compose.yml up -d redis postgres
alembic upgrade head
python -m baccarat.app
```

## Architecture summary

```
Polymarket WS ─┐                      ┌─► Strategy (Arb / Copy) ─► Risk ─► Executor ─► CLOB / Polygon
               ├─► asyncio.Queue ─────┤                               │
Polygon RPC  ──┘                      └─► Redis (orderbook, position) ┘
                                              │
                                              └─► Postgres (truth)
```

- **Single event loop** orchestrates all I/O. No thread pools, no inter-process locks.
- **Maker-Taker arbitrage** — never submits both legs in parallel. The thin leg
  is placed as a Maker; the thick leg fires only after `OrderFilled` confirmation.
  A hard hedge fallback unwinds any naked exposure; if the hedge itself fails,
  the strategy halts and pages an operator via Telegram.
- **Risk manager** reads positions from a Redis mirror (μs reads) and writes
  to Postgres asynchronously (fault-tolerant truth).
- **Trace ID** — every `Signal.id` is set as a contextvar at strategy entry
  and is included in every structlog event downstream. One `grep` reconstructs
  the full lifecycle.

## Configuration

- Non-sensitive defaults live in `config/settings.yaml` (see `settings.example.yaml`).
- Secrets live only in `.env` (private key, RPC URLs, DB passwords, Telegram token).
- Both are merged by `baccarat.core.config.Settings` (Pydantic Settings).

## Conventions

- All money/price values are `decimal.Decimal`. **Never use `float`** for prices,
  sizes, or PnL — even one stray float can corrupt downstream rounding.
- All times are UTC, expressed as `int` epoch ms in transit and `TIMESTAMPTZ`
  at rest.
- Async-only API — every public function on every base class is `async def`.

## Roadmap

- **M1** — Architecture init (this milestone).
- **M2** — Polymarket CLOB WS subscription + Polygon listener wiring.
- **M3** — CopyTrade & Arbitrage strategies + unit tests (incl. slippage edge cases).
- **M4** — Live trading: USDC approve / buy / sell / merge-redeem on Polygon mainnet.

## License

Proprietary — internal use only.
