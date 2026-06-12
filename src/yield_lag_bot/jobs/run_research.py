"""Run a lead-lag report from a CSV file."""

from __future__ import annotations

import argparse

import pandas as pd

from yield_lag_bot.research.lead_lag_analyzer import LeadLagAnalyzer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("output_csv")
    parser.add_argument("--cme-symbol", default="ZN")
    parser.add_argument("--crypto-symbol", default="BTCUSDT")
    args = parser.parse_args()

    ticks = pd.read_csv(args.input_csv)
    results = LeadLagAnalyzer().analyze_pair(
        ticks,
        cme_symbol=args.cme_symbol,
        crypto_symbol=args.crypto_symbol,
    )
    LeadLagAnalyzer().write_report(results, args.output_csv)


if __name__ == "__main__":
    main()
