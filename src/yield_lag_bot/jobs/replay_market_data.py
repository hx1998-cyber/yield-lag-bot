"""Replay saved ticks through the lead-lag analyzer path."""

from __future__ import annotations

import argparse

import pandas as pd

from yield_lag_bot.research.lead_lag_analyzer import LeadLagAnalyzer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--out", default="lead_lag_report.csv")
    parser.add_argument("--cme-symbol", default="ZN")
    parser.add_argument("--crypto-symbol", default="BTC")
    args = parser.parse_args()

    ticks = pd.read_csv(args.input_csv)
    analyzer = LeadLagAnalyzer()
    results = analyzer.analyze_pair(
        ticks,
        cme_symbol=args.cme_symbol,
        crypto_symbol=args.crypto_symbol,
    )
    analyzer.write_report(results, args.out)
    print(f"wrote {len(results)} rows to {args.out}")


if __name__ == "__main__":
    main()
