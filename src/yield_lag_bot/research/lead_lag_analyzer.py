"""Lead-lag research utilities."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from pathlib import Path

import pandas as pd

from yield_lag_bot.research.fee_slippage_model import estimate_cost_bps

DEFAULT_WINDOWS_MS = (100, 250, 500, 1000, 3000, 5000)
REPORT_COLUMNS = [
    "cme_symbol",
    "crypto_symbol",
    "window_ms",
    "horizon_ms",
    "sample_count",
    "correlation",
    "hit_rate",
    "average_forward_return_bps",
    "estimated_fee_bps",
    "estimated_slippage_bps",
    "net_forward_return_bps",
]


@dataclass(frozen=True, slots=True)
class LeadLagResult:
    cme_symbol: str
    crypto_symbol: str
    window_ms: int
    horizon_ms: int
    sample_count: int
    correlation: float
    hit_rate: float
    average_forward_return_bps: float
    estimated_fee_bps: float
    estimated_slippage_bps: float
    net_forward_return_bps: float


class LeadLagAnalyzer:
    def __init__(
        self,
        *,
        windows_ms: tuple[int, ...] = DEFAULT_WINDOWS_MS,
        horizons_ms: tuple[int, ...] | None = None,
        estimated_fee_bps: float = 5.0,
        estimated_slippage_bps: float = 2.0,
    ) -> None:
        self.windows_ms = windows_ms
        self.horizons_ms = horizons_ms or windows_ms
        self.estimated_fee_bps, self.estimated_slippage_bps = estimate_cost_bps(
            fee_bps=estimated_fee_bps,
            slippage_bps=estimated_slippage_bps,
        )

    def prepare_ticks(self, ticks: pd.DataFrame) -> pd.DataFrame:
        required = {"symbol", "receive_ts"}
        missing = required - set(ticks.columns)
        if missing:
            raise ValueError(f"ticks missing required columns: {sorted(missing)}")
        df = ticks.copy()
        df["receive_ts"] = pd.to_datetime(df["receive_ts"], utc=True)
        if "mid_price" not in df.columns:
            df["mid_price"] = (pd.to_numeric(df["bid_price"]) + pd.to_numeric(df["ask_price"])) / 2
        df = df.dropna(subset=["mid_price"]).sort_values("receive_ts")
        return df

    def align_symbol_pair(
        self,
        ticks: pd.DataFrame,
        *,
        cme_symbol: str,
        crypto_symbol: str,
        frequency_ms: int,
    ) -> pd.DataFrame:
        df = self.prepare_ticks(ticks)
        frame = (
            df[df["symbol"].isin([cme_symbol, crypto_symbol])]
            .pivot_table(index="receive_ts", columns="symbol", values="mid_price", aggfunc="last")
            .sort_index()
            .resample(f"{frequency_ms}ms")
            .last()
            .ffill()
            .dropna(subset=[cme_symbol, crypto_symbol])
        )
        return frame

    def analyze_pair(
        self,
        ticks: pd.DataFrame,
        *,
        cme_symbol: str,
        crypto_symbol: str,
    ) -> list[LeadLagResult]:
        results: list[LeadLagResult] = []
        for window_ms in self.windows_ms:
            aligned = self.align_symbol_pair(
                ticks,
                cme_symbol=cme_symbol,
                crypto_symbol=crypto_symbol,
                frequency_ms=window_ms,
            )
            if aligned.empty:
                continue
            cme_return = aligned[cme_symbol].pct_change()
            for horizon_ms in self.horizons_ms:
                periods = max(1, round(horizon_ms / window_ms))
                crypto_forward = aligned[crypto_symbol].shift(-periods) / aligned[crypto_symbol] - 1
                sample = pd.concat(
                    [cme_return.rename("cme_return"), crypto_forward.rename("crypto_forward")],
                    axis=1,
                ).dropna()
                if sample.empty:
                    continue
                correlation = self._safe_correlation(sample["cme_return"], sample["crypto_forward"])
                direction = sample["cme_return"] * sample["crypto_forward"]
                avg_bps = float(sample["crypto_forward"].mean() * 10_000)
                costs = self.estimated_fee_bps + self.estimated_slippage_bps
                results.append(
                    LeadLagResult(
                        cme_symbol=cme_symbol,
                        crypto_symbol=crypto_symbol,
                        window_ms=window_ms,
                        horizon_ms=horizon_ms,
                        sample_count=len(sample),
                        correlation=correlation,
                        hit_rate=float((direction > 0).mean()),
                        average_forward_return_bps=avg_bps,
                        estimated_fee_bps=self.estimated_fee_bps,
                        estimated_slippage_bps=self.estimated_slippage_bps,
                        net_forward_return_bps=avg_bps - costs,
                    )
                )
        return results

    def write_report(self, results: list[LeadLagResult], path: str | Path) -> None:
        rows = [self._result_to_mapping(result) for result in results]
        pd.DataFrame(rows, columns=REPORT_COLUMNS).to_csv(path, index=False)

    @staticmethod
    def _safe_correlation(left: pd.Series, right: pd.Series) -> float:
        sample = pd.concat([left, right], axis=1).dropna()
        if len(sample) < 2:
            return float("nan")
        if sample.iloc[:, 0].std() == 0 or sample.iloc[:, 1].std() == 0:
            return float("nan")
        return float(sample.iloc[:, 0].corr(sample.iloc[:, 1]))

    @staticmethod
    def _result_to_mapping(result: LeadLagResult) -> dict[str, object]:
        if is_dataclass(result):
            return asdict(result)
        if hasattr(result, "_asdict"):
            return dict(result._asdict())
        if hasattr(result, "model_dump"):
            return dict(result.model_dump())
        return {field.name: getattr(result, field.name, None) for field in fields(LeadLagResult)}
