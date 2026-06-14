"""Analyze offline research feature panels for conditional signal behavior."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

BIN_LABELS = ["0_to_0.25", "0.25_to_0.5", "0.5_to_1.0", "1.0_to_2.0", "2.0_plus"]
BIN_EDGES = [-float("inf"), 0.25, 0.5, 1.0, 2.0, float("inf")]
OUTPUT_COLUMNS = [
    "group_type",
    "group_key",
    "rows",
    "inverse_correct_1m_rate",
    "avg_eth_forward_return_1m_bps",
    "median_eth_forward_return_1m_bps",
    "avg_abs_cme_return_bps",
    "avg_curve_abs_return_bps_max",
    "positive_eth_forward_rate",
    "negative_eth_forward_rate",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--markdown", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    analyze_research_features(features=args.features, out=args.out, markdown=args.markdown)


def analyze_research_features(*, features: str | Path, out: str | Path, markdown: str | Path) -> pd.DataFrame:
    features_path = Path(features)
    out_path = Path(out)
    markdown_path = Path(markdown)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)

    if not features_path.exists():
        diagnostics = _empty_diagnostics()
        diagnostics.to_csv(out_path, index=False)
        markdown_path.write_text(
            _report_markdown(diagnostics, pd.DataFrame(), warning=f"Feature panel not found: {features_path}"),
            encoding="utf-8",
        )
        return diagnostics

    features_frame = _prepare_features(pd.read_csv(features_path))
    diagnostics = _build_diagnostics(features_frame)
    diagnostics.to_csv(out_path, index=False)
    markdown_path.write_text(_report_markdown(diagnostics, features_frame), encoding="utf-8")
    return diagnostics


def _prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    numeric_columns = [
        "inverse_correct_1m",
        "eth_forward_return_1m_bps",
        "abs_cme_return_bps",
        "curve_abs_return_bps_max",
        "curve_abs_return_bps_avg",
        "curve_symbol_count",
        "curve_up_count",
        "curve_down_count",
        "curve_net_direction",
    ]
    for column in numeric_columns:
        if column in prepared.columns:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
    if "inverse_correct_1m" in prepared.columns:
        prepared["inverse_correct_1m"] = prepared["inverse_correct_1m"].map(_bool_value)
    prepared["abs_cme_return_bps_bin"] = _bin_values(prepared.get("abs_cme_return_bps", pd.Series(dtype=float)))
    prepared["curve_abs_return_bps_avg_bin"] = _bin_values(
        prepared.get("curve_abs_return_bps_avg", pd.Series(dtype=float))
    )
    prepared["curve_abs_return_bps_max_bin"] = _bin_values(
        prepared.get("curve_abs_return_bps_max", pd.Series(dtype=float))
    )
    prepared["curve_consensus_label"] = prepared.apply(_curve_consensus_label, axis=1)
    return prepared


def _bin_values(values: pd.Series) -> pd.Series:
    return pd.cut(values.fillna(0.0), bins=BIN_EDGES, labels=BIN_LABELS, right=False).astype(str)


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes"}


def _curve_consensus_label(row: pd.Series) -> str:
    up_count = int(row.get("curve_up_count", 0) or 0)
    down_count = int(row.get("curve_down_count", 0) or 0)
    if up_count >= 2 and down_count == 0:
        return "curve_consensus_up"
    if down_count >= 2 and up_count == 0:
        return "curve_consensus_down"
    if up_count > 0 and down_count > 0:
        return "mixed_curve"
    return "no_consensus"


def _build_diagnostics(features: pd.DataFrame) -> pd.DataFrame:
    if features.empty:
        return _empty_diagnostics()
    frames = [
        _group_diagnostic(features, "cme_symbol", "cme_symbol"),
        _group_diagnostic(features, "date", "date"),
        _group_diagnostic(features, "event_name", "event_name"),
        _group_diagnostic(features, "candidate_tier", "candidate_tier"),
        _group_diagnostic(features, "abs_cme_return_bps_bin", "abs_cme_return_bps_bin"),
        _group_diagnostic(features, "curve_symbol_count", "curve_symbol_count"),
        _group_diagnostic(features, "curve_net_direction", "curve_net_direction"),
        _group_diagnostic(features, "curve_abs_return_bps_avg_bin", "curve_abs_return_bps_avg_bin")
        if "curve_abs_return_bps_avg_bin" in features.columns
        else _empty_diagnostics(),
        _group_diagnostic(features, "curve_abs_return_bps_max_bin", "curve_abs_return_bps_max_bin"),
        _conditional_diagnostics(features),
    ]
    diagnostics = pd.concat(frames, ignore_index=True)
    return diagnostics.reindex(columns=OUTPUT_COLUMNS)


def _group_diagnostic(features: pd.DataFrame, column: str, group_type: str) -> pd.DataFrame:
    if column not in features.columns:
        return _empty_diagnostics()
    rows = []
    for key, group in features.groupby(column, dropna=False):
        rows.append(_diagnostic_row(group_type, str(key), group))
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS) if rows else _empty_diagnostics()


def _conditional_diagnostics(features: pd.DataFrame) -> pd.DataFrame:
    conditions = {
        "high_cme_move": features["abs_cme_return_bps"] >= 0.5,
        "very_high_cme_move": features["abs_cme_return_bps"] >= 1.0,
        "curve_consensus_up": (features["curve_up_count"] >= 2) & (features["curve_down_count"] == 0),
        "curve_consensus_down": (features["curve_down_count"] >= 2) & (features["curve_up_count"] == 0),
        "mixed_curve": (features["curve_up_count"] > 0) & (features["curve_down_count"] > 0),
    }
    rows = [_diagnostic_row("condition", key, features[mask]) for key, mask in conditions.items()]
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def _diagnostic_row(group_type: str, group_key: str, group: pd.DataFrame) -> dict[str, object]:
    rows = len(group)
    if rows == 0:
        return {
            "group_type": group_type,
            "group_key": group_key,
            "rows": 0,
            "inverse_correct_1m_rate": 0.0,
            "avg_eth_forward_return_1m_bps": 0.0,
            "median_eth_forward_return_1m_bps": 0.0,
            "avg_abs_cme_return_bps": 0.0,
            "avg_curve_abs_return_bps_max": 0.0,
            "positive_eth_forward_rate": 0.0,
            "negative_eth_forward_rate": 0.0,
        }
    eth = group["eth_forward_return_1m_bps"]
    return {
        "group_type": group_type,
        "group_key": group_key,
        "rows": rows,
        "inverse_correct_1m_rate": float(group["inverse_correct_1m"].mean()),
        "avg_eth_forward_return_1m_bps": float(eth.mean()),
        "median_eth_forward_return_1m_bps": float(eth.median()),
        "avg_abs_cme_return_bps": float(group["abs_cme_return_bps"].mean()),
        "avg_curve_abs_return_bps_max": float(group["curve_abs_return_bps_max"].mean()),
        "positive_eth_forward_rate": float((eth > 0).mean()),
        "negative_eth_forward_rate": float((eth < 0).mean()),
    }


def _empty_diagnostics() -> pd.DataFrame:
    return pd.DataFrame(columns=OUTPUT_COLUMNS)


def _report_markdown(
    diagnostics: pd.DataFrame,
    features: pd.DataFrame,
    *,
    warning: str | None = None,
) -> str:
    total_rows = len(features)
    overall_rate = float(features["inverse_correct_1m"].mean()) if total_rows else 0.0
    lines = [
        "# M5B Feature Diagnostics",
        "",
        "Research-only diagnostics. This is not a trading strategy and does not simulate PnL.",
        "",
    ]
    if warning is not None:
        lines.extend(["## Warning", "", warning, ""])
    lines.extend(
        [
            f"- total rows: {total_rows}",
            f"- overall inverse_correct_1m rate: {overall_rate:.2%}",
            "",
            "## Best Bins By Inverse Correct Rate",
            "",
        ]
    )
    min_rows = diagnostics[diagnostics["rows"] >= 20]
    lines.extend(_markdown_table(min_rows.sort_values("inverse_correct_1m_rate", ascending=False).head(10)))
    lines.extend(["", "## Best Bins By Average ETH Forward Return", ""])
    lines.extend(_markdown_table(min_rows.sort_values("avg_eth_forward_return_1m_bps", ascending=False).head(10)))
    lines.extend(["", "## Weak Or No-Signal Bins", ""])
    weak = min_rows[min_rows["inverse_correct_1m_rate"] < 0.45]
    lines.extend(_markdown_table(weak.sort_values("inverse_correct_1m_rate").head(10)))
    lines.extend(["", "## Conditional Reads", ""])
    lines.extend(_conditional_read_lines(diagnostics))
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "This feature remains research-only. It must not be used as a trading strategy, live signal, "
            "order-placement input, or private-API workflow.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _conditional_read_lines(diagnostics: pd.DataFrame) -> list[str]:
    def rate(key: str) -> float:
        rows = diagnostics[(diagnostics["group_type"] == "condition") & (diagnostics["group_key"] == key)]
        return float(rows.iloc[0]["inverse_correct_1m_rate"]) if not rows.empty else 0.0

    high = rate("high_cme_move")
    very_high = rate("very_high_cme_move")
    up = rate("curve_consensus_up")
    down = rate("curve_consensus_down")
    mixed = rate("mixed_curve")
    return [
        f"- high CME move inverse correctness: {high:.2%}",
        f"- very high CME move inverse correctness: {very_high:.2%}",
        f"- curve consensus up inverse correctness: {up:.2%}",
        f"- curve consensus down inverse correctness: {down:.2%}",
        f"- mixed curve inverse correctness: {mixed:.2%}",
        f"- high CME move improves correctness: {high > mixed}",
        f"- curve consensus improves correctness: {max(up, down) > mixed}",
    ]


def _markdown_table(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return ["No rows."]
    clean = frame.copy()
    for column in clean.columns:
        if pd.api.types.is_float_dtype(clean[column]):
            clean[column] = clean[column].map(lambda value: "" if pd.isna(value) else f"{value:.6f}")
    header = "| " + " | ".join(clean.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(clean.columns)) + " |"
    rows = [
        "| " + " | ".join("" if pd.isna(value) else str(value) for value in row)
        + " |"
        for row in clean.itertuples(index=False, name=None)
    ]
    return [header, separator, *rows]


if __name__ == "__main__":
    main()
