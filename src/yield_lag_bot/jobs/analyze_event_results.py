"""Analyze aggregate event-study results and rank candidate windows."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

HORIZONS = ("1m", "3m", "5m")
MIN_SAMPLE_COUNT = 60
DEFAULT_MIN_CME_NONZERO_RETURN_COUNT = 10
RANKING_COLUMNS = [
    "abs_correlation_1m",
    "abs_correlation_3m",
    "abs_correlation_5m",
    "best_horizon",
    "best_abs_correlation",
    "best_direction_hit_rate",
    "signal_direction",
    "candidate_score",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--markdown", required=True)
    parser.add_argument(
        "--min-cme-nonzero-return-count",
        type=int,
        default=DEFAULT_MIN_CME_NONZERO_RETURN_COUNT,
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    analyze_event_results(
        summary=args.summary,
        out=args.out,
        markdown=args.markdown,
        min_cme_nonzero_return_count=args.min_cme_nonzero_return_count,
    )


def analyze_event_results(
    *,
    summary: str | Path,
    out: str | Path,
    markdown: str | Path,
    min_cme_nonzero_return_count: int = DEFAULT_MIN_CME_NONZERO_RETURN_COUNT,
) -> pd.DataFrame:
    summary_path = Path(summary)
    out_path = Path(out)
    markdown_path = Path(markdown)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)

    if not summary_path.exists():
        ranked = _empty_ranked_frame()
        ranked.to_csv(out_path, index=False)
        markdown_path.write_text(
            _missing_summary_notes(summary_path, min_cme_nonzero_return_count),
            encoding="utf-8",
        )
        return ranked

    source = pd.read_csv(summary_path)
    source = _normalize_numeric_columns(source)
    ranked = _rank_candidates(source, min_cme_nonzero_return_count=min_cme_nonzero_return_count)
    ranked.to_csv(out_path, index=False)
    markdown_path.write_text(
        _research_notes(
            source=source,
            ranked=ranked,
            summary_path=summary_path,
            ranked_path=out_path,
            min_cme_nonzero_return_count=min_cme_nonzero_return_count,
        ),
        encoding="utf-8",
    )
    return ranked


def _rank_candidates(
    source: pd.DataFrame,
    *,
    min_cme_nonzero_return_count: int,
) -> pd.DataFrame:
    candidates = _eligible_rows(
        source,
        min_cme_nonzero_return_count=min_cme_nonzero_return_count,
    ).copy()
    if candidates.empty:
        return _empty_ranked_frame(source)

    candidates = _add_ranking_columns(candidates)
    candidates = candidates.sort_values(
        ["candidate_score", "best_abs_correlation", "cme_nonzero_return_count"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    return candidates


def _eligible_rows(
    source: pd.DataFrame,
    *,
    min_cme_nonzero_return_count: int,
) -> pd.DataFrame:
    if source.empty:
        return source
    required = {"status", "quality_status", "sample_count", "cme_nonzero_return_count"}
    if not required.issubset(source.columns):
        return source.iloc[0:0].copy()
    quality = source["quality_status"].fillna("").astype(str).str.lower()
    status = source["status"].fillna("").astype(str).str.lower()
    return source[
        (status == "ok")
        & (quality.isin({"ok", "warning"}))
        & (source["sample_count"] >= MIN_SAMPLE_COUNT)
        & (source["cme_nonzero_return_count"] >= min_cme_nonzero_return_count)
    ]


def _add_ranking_columns(frame: pd.DataFrame) -> pd.DataFrame:
    ranked = frame.copy()
    for horizon in HORIZONS:
        ranked[f"abs_correlation_{horizon}"] = ranked[f"correlation_{horizon}"].abs()

    best_horizons: list[str] = []
    best_abs_correlations: list[float] = []
    best_hit_rates: list[float] = []
    signal_directions: list[str] = []
    candidate_scores: list[float] = []

    for _, row in ranked.iterrows():
        best_horizon, best_correlation, best_abs_correlation = _best_correlation(row)
        best_hit_rate = _numeric_value(row.get(f"direction_hit_rate_{best_horizon}", float("nan")))
        hit_edge = abs(best_hit_rate - 0.5) * 2 if pd.notna(best_hit_rate) else 0.0
        nonzero_count = _numeric_value(row.get("cme_nonzero_return_count", 0.0))
        movement_score = min(max(nonzero_count, 0.0) / 120.0, 1.0)
        candidate_score = (best_abs_correlation * 70.0) + (hit_edge * 20.0) + (movement_score * 10.0)

        best_horizons.append(best_horizon)
        best_abs_correlations.append(best_abs_correlation)
        best_hit_rates.append(best_hit_rate)
        signal_directions.append(_signal_direction(best_correlation))
        candidate_scores.append(round(candidate_score, 6))

    ranked["best_horizon"] = best_horizons
    ranked["best_abs_correlation"] = best_abs_correlations
    ranked["best_direction_hit_rate"] = best_hit_rates
    ranked["signal_direction"] = signal_directions
    ranked["candidate_score"] = candidate_scores
    return ranked


def _best_correlation(row: pd.Series) -> tuple[str, float, float]:
    best_horizon = "1m"
    best_correlation = float("nan")
    best_abs_correlation = -1.0
    for horizon in HORIZONS:
        value = _numeric_value(row.get(f"correlation_{horizon}", float("nan")))
        abs_value = abs(value) if pd.notna(value) else -1.0
        if abs_value > best_abs_correlation:
            best_horizon = horizon
            best_correlation = value
            best_abs_correlation = abs_value
    if best_abs_correlation < 0:
        return best_horizon, float("nan"), 0.0
    return best_horizon, best_correlation, best_abs_correlation


def _signal_direction(best_correlation: float) -> str:
    if pd.isna(best_correlation):
        return ""
    if best_correlation > 0:
        return "positive"
    if best_correlation < 0:
        return "inverse"
    return ""


def _normalize_numeric_columns(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    numeric_columns = [
        "sample_count",
        "cme_nonzero_return_count",
        "correlation_1m",
        "correlation_3m",
        "correlation_5m",
        "direction_hit_rate_1m",
        "direction_hit_rate_3m",
        "direction_hit_rate_5m",
    ]
    for column in numeric_columns:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    return normalized


def _numeric_value(value: object) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0])


def _empty_ranked_frame(source: pd.DataFrame | None = None) -> pd.DataFrame:
    source_columns = [] if source is None else list(source.columns)
    columns = source_columns + [column for column in RANKING_COLUMNS if column not in source_columns]
    return pd.DataFrame(columns=columns)


def _research_notes(
    *,
    source: pd.DataFrame,
    ranked: pd.DataFrame,
    summary_path: Path,
    ranked_path: Path,
    min_cme_nonzero_return_count: int,
) -> str:
    lines = [
        "# M3H Event Study Result Analysis",
        "",
        f"Source summary: `{summary_path}`",
        f"Ranked output: `{ranked_path}`",
        "",
        "Candidate score = 70 * best absolute correlation + "
        "20 * abs(direction hit rate - 0.5) * 2 + "
        "10 * min(cme_nonzero_return_count / 120, 1).",
        f"Filters: status `ok`, quality_status `ok` or `warning`, sample_count >= {MIN_SAMPLE_COUNT}, "
        f"cme_nonzero_return_count >= {min_cme_nonzero_return_count}.",
        "",
        "## Top 10 Candidate Windows",
        "",
    ]
    lines.extend(_markdown_table(_top_candidate_rows(ranked)))
    lines.extend(["", "## Weak Or No-Signal Windows", ""])
    lines.extend(_markdown_table(_weak_rows(source, min_cme_nonzero_return_count=min_cme_nonzero_return_count)))
    lines.extend(["", "## Insufficient Data Warnings", ""])
    lines.extend(
        _markdown_table(
            _insufficient_rows(
                source,
                min_cme_nonzero_return_count=min_cme_nonzero_return_count,
            )
        )
    )
    lines.extend(["", "## Recommended Next Windows To Test", ""])
    lines.extend(_recommendations(ranked))
    return "\n".join(lines).rstrip() + "\n"


def _missing_summary_notes(summary_path: Path, min_cme_nonzero_return_count: int) -> str:
    return "\n".join(
        [
            "# M3H Event Study Result Analysis",
            "",
            f"Source summary was not found: `{summary_path}`",
            "",
            "No candidate rows were ranked.",
            "",
            "## Insufficient Data Warnings",
            "",
            f"- Missing M3G aggregate summary. Run M3G first, then rerun M3H with "
            f"`--min-cme-nonzero-return-count {min_cme_nonzero_return_count}` if needed.",
        ]
    ) + "\n"


def _top_candidate_rows(ranked: pd.DataFrame) -> pd.DataFrame:
    if ranked.empty:
        return pd.DataFrame()
    return ranked.head(10)[_note_columns(ranked)]


def _weak_rows(source: pd.DataFrame, *, min_cme_nonzero_return_count: int) -> pd.DataFrame:
    eligible = _eligible_rows(source, min_cme_nonzero_return_count=min_cme_nonzero_return_count)
    if eligible.empty:
        return pd.DataFrame()
    ranked = _add_ranking_columns(eligible)
    weak = ranked[(ranked["best_abs_correlation"] < 0.10) | ((ranked["best_direction_hit_rate"] - 0.5).abs() < 0.05)]
    return weak.sort_values("best_abs_correlation", ascending=True).head(10)[_note_columns(weak)]


def _insufficient_rows(source: pd.DataFrame, *, min_cme_nonzero_return_count: int) -> pd.DataFrame:
    if source.empty:
        return pd.DataFrame()
    required = {"status", "quality_status", "sample_count", "cme_nonzero_return_count"}
    if not required.issubset(source.columns):
        return pd.DataFrame(
            [
                {
                    "reason": f"summary missing required columns: {sorted(required - set(source.columns))}",
                    "row_count": len(source),
                }
            ]
        )
    rows = source.copy()
    rows["warning_reason"] = rows.apply(
        lambda row: _warning_reason(row, min_cme_nonzero_return_count=min_cme_nonzero_return_count),
        axis=1,
    )
    rows = rows[rows["warning_reason"] != ""]
    if rows.empty:
        return pd.DataFrame()
    wanted = [
        "event_name",
        "cme_symbol",
        "crypto_symbol",
        "status",
        "quality_status",
        "sample_count",
        "cme_nonzero_return_count",
        "warning_reason",
    ]
    columns = [column for column in wanted if column in rows.columns]
    return rows[columns].head(15)


def _warning_reason(row: pd.Series, *, min_cme_nonzero_return_count: int) -> str:
    reasons = []
    if str(row.get("status", "")).lower() != "ok":
        reasons.append("status not ok")
    if str(row.get("quality_status", "")).lower() not in {"ok", "warning"}:
        reasons.append("quality status filtered")
    if _numeric_value(row.get("sample_count", 0)) < MIN_SAMPLE_COUNT:
        reasons.append("sample_count below 60")
    if _numeric_value(row.get("cme_nonzero_return_count", 0)) < min_cme_nonzero_return_count:
        reasons.append("too few nonzero CME returns")
    return "; ".join(reasons)


def _recommendations(ranked: pd.DataFrame) -> list[str]:
    if ranked.empty:
        return [
            "- No eligible candidates yet. Add more event windows or lower the nonzero CME threshold "
            "for diagnostics only."
        ]
    recommendations = []
    for _, row in ranked.head(5).iterrows():
        event_name = row.get("event_name", "unknown_event")
        cme_symbol = row.get("cme_symbol", "")
        crypto_symbol = row.get("crypto_symbol", "")
        horizon = row.get("best_horizon", "")
        direction = row.get("signal_direction", "")
        recommendations.append(
            f"- Retest `{event_name}` for `{cme_symbol}` -> `{crypto_symbol}` around the {horizon} "
            f"horizon; current signal is {direction or 'flat'} with score {row.get('candidate_score', 0)}."
        )
    return recommendations


def _note_columns(frame: pd.DataFrame) -> list[str]:
    wanted = [
        "event_name",
        "event_time_utc",
        "cme_symbol",
        "crypto_symbol",
        "sample_count",
        "cme_nonzero_return_count",
        "best_horizon",
        "best_abs_correlation",
        "best_direction_hit_rate",
        "signal_direction",
        "candidate_score",
    ]
    return [column for column in wanted if column in frame.columns]


def _markdown_table(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return ["No rows."]
    clean = frame.copy()
    for column in clean.columns:
        if pd.api.types.is_float_dtype(clean[column]):
            clean[column] = clean[column].map(lambda value: "" if pd.isna(value) else f"{value:.4f}")
    header = "| " + " | ".join(clean.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(clean.columns)) + " |"
    rows = [
        "| " + " | ".join("" if pd.isna(value) else str(value) for value in row) + " |"
        for row in clean.itertuples(index=False, name=None)
    ]
    return [header, separator, *rows]


if __name__ == "__main__":
    main()
