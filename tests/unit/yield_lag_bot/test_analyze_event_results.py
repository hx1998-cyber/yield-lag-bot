from __future__ import annotations

import pandas as pd

from yield_lag_bot.jobs.analyze_event_results import analyze_event_results


def test_analyzer_parses_summary_and_writes_outputs(tmp_path) -> None:
    summary_path = tmp_path / "summary.csv"
    ranked_path = tmp_path / "ranked_summary.csv"
    notes_path = tmp_path / "research_notes.md"
    _write_summary(summary_path)

    ranked = analyze_event_results(summary=summary_path, out=ranked_path, markdown=notes_path)

    written = pd.read_csv(ranked_path)
    notes = notes_path.read_text(encoding="utf-8")
    assert len(ranked) == 3
    assert list(written["event_name"]) == ["fomc_hot", "fomc_inverse", "payrolls_warning"]
    assert "Top 10 Candidate Windows" in notes
    assert "Recommended Next Windows To Test" in notes


def test_analyzer_filters_bad_rows(tmp_path) -> None:
    summary_path = tmp_path / "summary.csv"
    ranked_path = tmp_path / "ranked_summary.csv"
    notes_path = tmp_path / "research_notes.md"
    _write_summary(summary_path)

    ranked = analyze_event_results(
        summary=summary_path,
        out=ranked_path,
        markdown=notes_path,
        min_cme_nonzero_return_count=10,
    )

    assert set(ranked["event_name"]) == {"fomc_hot", "fomc_inverse", "payrolls_warning"}
    assert "failed_event" not in set(ranked["event_name"])
    assert "low_sample" not in set(ranked["event_name"])
    assert "low_cme_movement" not in set(ranked["event_name"])
    assert "bad_quality" not in set(ranked["event_name"])


def test_analyzer_ranks_candidate_rows_and_adds_signal_columns(tmp_path) -> None:
    summary_path = tmp_path / "summary.csv"
    ranked_path = tmp_path / "ranked_summary.csv"
    notes_path = tmp_path / "research_notes.md"
    _write_summary(summary_path)

    ranked = analyze_event_results(summary=summary_path, out=ranked_path, markdown=notes_path)
    top = ranked.iloc[0]
    inverse = ranked[ranked["event_name"] == "fomc_inverse"].iloc[0]

    assert top["event_name"] == "fomc_hot"
    assert top["best_horizon"] == "3m"
    assert top["best_abs_correlation"] == 0.42
    assert top["best_direction_hit_rate"] == 0.64
    assert top["signal_direction"] == "positive"
    assert top["candidate_score"] > inverse["candidate_score"]
    assert inverse["best_horizon"] == "5m"
    assert inverse["signal_direction"] == "inverse"


def test_analyzer_writes_markdown_sections(tmp_path) -> None:
    summary_path = tmp_path / "summary.csv"
    ranked_path = tmp_path / "ranked_summary.csv"
    notes_path = tmp_path / "research_notes.md"
    _write_summary(summary_path)

    analyze_event_results(summary=summary_path, out=ranked_path, markdown=notes_path)

    notes = notes_path.read_text(encoding="utf-8")
    assert "Weak Or No-Signal Windows" in notes
    assert "Insufficient Data Warnings" in notes
    assert "low_sample" in notes
    assert "sample_count below 60" in notes


def test_analyzer_handles_missing_summary_gracefully(tmp_path) -> None:
    summary_path = tmp_path / "missing_summary.csv"
    ranked_path = tmp_path / "ranked_summary.csv"
    notes_path = tmp_path / "research_notes.md"

    ranked = analyze_event_results(summary=summary_path, out=ranked_path, markdown=notes_path)

    assert ranked.empty
    assert ranked_path.exists()
    assert notes_path.exists()
    assert "Source summary was not found" in notes_path.read_text(encoding="utf-8")


def test_analyzer_min_sample_count_filter(tmp_path) -> None:
    summary_path = tmp_path / "summary.csv"
    ranked_path = tmp_path / "ranked_summary.csv"
    notes_path = tmp_path / "research_notes.md"
    _write_summary(summary_path)

    ranked = analyze_event_results(
        summary=summary_path,
        out=ranked_path,
        markdown=notes_path,
        min_sample_count=100,
    )

    assert set(ranked["event_name"]) == {"fomc_hot", "fomc_inverse"}
    assert "payrolls_warning" not in set(ranked["event_name"])
    assert "sample_count below 100" in notes_path.read_text(encoding="utf-8")


def test_analyzer_aligned_direction_hit_rate_for_inverse_rows(tmp_path) -> None:
    summary_path = tmp_path / "summary.csv"
    ranked_path = tmp_path / "ranked_summary.csv"
    notes_path = tmp_path / "research_notes.md"
    _write_summary(summary_path)

    ranked = analyze_event_results(summary=summary_path, out=ranked_path, markdown=notes_path)
    inverse = ranked[ranked["event_name"] == "fomc_inverse"].iloc[0]

    assert inverse["signal_direction"] == "inverse"
    assert inverse["best_direction_hit_rate"] == 0.36
    assert inverse["directional_edge"] == 0.14
    assert inverse["aligned_direction_hit_rate"] == 0.64


def test_analyzer_candidate_tier_assignment(tmp_path) -> None:
    summary_path = tmp_path / "summary.csv"
    ranked_path = tmp_path / "ranked_summary.csv"
    notes_path = tmp_path / "research_notes.md"
    _write_summary(summary_path)

    ranked = analyze_event_results(summary=summary_path, out=ranked_path, markdown=notes_path)
    tiers = dict(zip(ranked["event_name"], ranked["candidate_tier"], strict=True))

    assert tiers["fomc_hot"] == "strong_candidate"
    assert tiers["fomc_inverse"] == "strong_candidate"
    assert tiers["payrolls_warning"] == "weak"


def test_analyzer_pair_summary_output(tmp_path) -> None:
    summary_path = tmp_path / "summary.csv"
    ranked_path = tmp_path / "ranked_summary.csv"
    notes_path = tmp_path / "research_notes.md"
    pair_summary_path = tmp_path / "pair_summary.csv"
    _write_summary(summary_path)

    analyze_event_results(
        summary=summary_path,
        out=ranked_path,
        markdown=notes_path,
        pair_summary_out=pair_summary_path,
    )

    pair_summary = pd.read_csv(pair_summary_path)
    assert set(pair_summary.columns) == {
        "cme_symbol",
        "crypto_symbol",
        "best_horizon",
        "signal_direction",
        "window_count",
        "avg_best_abs_correlation",
        "max_best_abs_correlation",
        "avg_aligned_direction_hit_rate",
        "avg_candidate_score",
        "watchlist_count",
        "strong_candidate_count",
    }
    inverse = pair_summary[
        (pair_summary["cme_symbol"] == "ZFM6")
        & (pair_summary["crypto_symbol"] == "ETH")
        & (pair_summary["best_horizon"] == "5m")
        & (pair_summary["signal_direction"] == "inverse")
    ].iloc[0]
    assert inverse["window_count"] == 1
    assert inverse["avg_best_abs_correlation"] == 0.32
    assert inverse["avg_aligned_direction_hit_rate"] == 0.64
    assert inverse["strong_candidate_count"] == 1
    assert inverse["watchlist_count"] == 0


def test_analyzer_positive_hit_rate_below_half_is_direction_inconsistent_and_weak(tmp_path) -> None:
    summary_path = tmp_path / "summary.csv"
    ranked_path = tmp_path / "ranked_summary.csv"
    notes_path = tmp_path / "research_notes.md"
    pd.DataFrame(
        [
            _row(
                event_name="positive_inconsistent",
                correlation_1m=0.30,
                correlation_3m=0.10,
                correlation_5m=0.05,
                direction_hit_rate_1m=0.30,
                cme_nonzero_return_count=30,
            )
        ]
    ).to_csv(summary_path, index=False)

    ranked = analyze_event_results(summary=summary_path, out=ranked_path, markdown=notes_path)
    row = ranked.iloc[0]

    assert row["signal_direction"] == "positive"
    assert row["aligned_direction_hit_rate"] == 0.30
    assert row["direction_consistent"] == False
    assert row["candidate_tier"] == "weak"
    assert "Direction Inconsistent Rows" in notes_path.read_text(encoding="utf-8")
    assert "aligned_direction_hit_rate < 0.5" in notes_path.read_text(encoding="utf-8")


def test_analyzer_inverse_hit_rate_below_half_can_be_candidate(tmp_path) -> None:
    summary_path = tmp_path / "summary.csv"
    ranked_path = tmp_path / "ranked_summary.csv"
    notes_path = tmp_path / "research_notes.md"
    pd.DataFrame(
        [
            _row(
                event_name="inverse_consistent",
                correlation_1m=-0.30,
                correlation_3m=-0.10,
                correlation_5m=-0.05,
                direction_hit_rate_1m=0.30,
                cme_nonzero_return_count=30,
            )
        ]
    ).to_csv(summary_path, index=False)

    ranked = analyze_event_results(summary=summary_path, out=ranked_path, markdown=notes_path)
    row = ranked.iloc[0]

    assert row["signal_direction"] == "inverse"
    assert row["aligned_direction_hit_rate"] == 0.70
    assert row["direction_consistent"] == True
    assert row["candidate_tier"] == "strong_candidate"


def test_analyzer_score_is_lower_for_direction_inconsistent_rows(tmp_path) -> None:
    summary_path = tmp_path / "summary.csv"
    ranked_path = tmp_path / "ranked_summary.csv"
    notes_path = tmp_path / "research_notes.md"
    pd.DataFrame(
        [
            _row(
                event_name="positive_inconsistent",
                correlation_1m=0.30,
                direction_hit_rate_1m=0.30,
                cme_nonzero_return_count=30,
            ),
            _row(
                event_name="inverse_consistent",
                correlation_1m=-0.30,
                direction_hit_rate_1m=0.30,
                cme_nonzero_return_count=30,
            ),
        ]
    ).to_csv(summary_path, index=False)

    ranked = analyze_event_results(summary=summary_path, out=ranked_path, markdown=notes_path)
    scores = dict(zip(ranked["event_name"], ranked["candidate_score"], strict=True))

    assert scores["positive_inconsistent"] < scores["inverse_consistent"]


def _write_summary(path) -> None:
    rows = [
        _row(
            event_name="fomc_hot",
            cme_symbol="ZNM6",
            crypto_symbol="BTC",
            sample_count=120,
            cme_nonzero_return_count=40,
            correlation_1m=0.12,
            correlation_3m=0.42,
            correlation_5m=0.30,
            direction_hit_rate_1m=0.55,
            direction_hit_rate_3m=0.64,
            direction_hit_rate_5m=0.60,
        ),
        _row(
            event_name="fomc_inverse",
            cme_symbol="ZFM6",
            crypto_symbol="ETH",
            sample_count=100,
            cme_nonzero_return_count=35,
            correlation_1m=-0.11,
            correlation_3m=-0.20,
            correlation_5m=-0.32,
            direction_hit_rate_1m=0.48,
            direction_hit_rate_3m=0.42,
            direction_hit_rate_5m=0.36,
        ),
        _row(
            event_name="payrolls_warning",
            quality_status="warning",
            sample_count=95,
            cme_nonzero_return_count=30,
            correlation_1m=0.08,
            correlation_3m=0.05,
            correlation_5m=0.04,
            direction_hit_rate_1m=0.51,
            direction_hit_rate_3m=0.52,
            direction_hit_rate_5m=0.50,
        ),
        _row(event_name="failed_event", status="failed", sample_count=120, cme_nonzero_return_count=40),
        _row(event_name="low_sample", sample_count=59, cme_nonzero_return_count=40),
        _row(event_name="low_cme_movement", sample_count=120, cme_nonzero_return_count=9),
        _row(
            event_name="bad_quality",
            quality_status="low_cme_movement",
            sample_count=120,
            cme_nonzero_return_count=40,
        ),
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def _row(
    *,
    event_name: str,
    event_time_utc: str = "2026-06-17T18:00:00Z",
    cme_symbol: str = "ZNM6",
    crypto_symbol: str = "BTC",
    status: str = "ok",
    quality_status: str = "ok",
    sample_count: int = 120,
    cme_nonzero_return_count: int = 30,
    correlation_1m: float = 0.02,
    correlation_3m: float = 0.03,
    correlation_5m: float = 0.04,
    direction_hit_rate_1m: float = 0.50,
    direction_hit_rate_3m: float = 0.50,
    direction_hit_rate_5m: float = 0.50,
) -> dict[str, object]:
    return {
        "event_name": event_name,
        "event_time_utc": event_time_utc,
        "cme_symbol": cme_symbol,
        "crypto_symbol": crypto_symbol,
        "start": "2026-06-17T17:00:00Z",
        "end": "2026-06-17T20:00:00Z",
        "status": status,
        "sample_count": sample_count,
        "cme_nonzero_return_count": cme_nonzero_return_count,
        "cme_abs_return_bps_max": 1.5,
        "correlation_1m": correlation_1m,
        "correlation_3m": correlation_3m,
        "correlation_5m": correlation_5m,
        "direction_hit_rate_1m": direction_hit_rate_1m,
        "direction_hit_rate_3m": direction_hit_rate_3m,
        "direction_hit_rate_5m": direction_hit_rate_5m,
        "quality_status": quality_status,
        "result_path": "",
        "summary_path": "",
        "error_message": "",
    }
