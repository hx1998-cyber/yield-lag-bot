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
