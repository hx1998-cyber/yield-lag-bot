from __future__ import annotations

import pandas as pd

from yield_lag_bot.jobs.run_experiment import load_experiment_config, run_experiment


def test_experiment_config_loading(tmp_path) -> None:
    cme_path = tmp_path / "cme.csv"
    crypto_path = tmp_path / "ticks_bbo.csv"
    config_path = tmp_path / "experiment.yaml"
    config_path.write_text(
        f"""
experiment_name: smoke
output_dir: out
windows:
  - name: macro
    start: "2024-01-01T00:00:00Z"
    end: "2024-01-01T00:00:01Z"
    cme_symbols: ["ZN"]
    crypto_symbols: ["BTC"]
    dataset: "local"
    schema: "csv"
    cme_csv: "{cme_path.name}"
    crypto_csv: "{crypto_path.name}"
""",
        encoding="utf-8",
    )

    config = load_experiment_config(config_path)

    assert config.experiment_name == "smoke"
    assert config.output_dir == tmp_path / "out"
    assert config.windows[0].name == "macro"
    assert config.windows[0].cme_symbols == ("ZN",)
    assert config.windows[0].crypto_symbols == ("BTC",)
    assert config.windows[0].cme_csv == cme_path
    assert config.windows[0].crypto_csv == crypto_path


def test_experiment_creates_expected_output_files(tmp_path) -> None:
    cme_path = tmp_path / "cme.csv"
    crypto_path = tmp_path / "ticks_bbo.csv"
    config_path = tmp_path / "experiment.yaml"
    cme_path.write_text(
        "timestamp,symbol,bid_price,ask_price,last_price\n"
        "2024-01-01T00:00:00.000Z,ZN,108.100,108.110,108.105\n"
        "2024-01-01T00:00:00.100Z,ZN,108.120,108.130,108.125\n"
        "2024-01-01T00:00:00.200Z,ZN,108.115,108.125,108.120\n",
        encoding="utf-8",
    )
    crypto_path.write_text(
        "symbol,receive_ts,bid_price,ask_price,last_price,mid_price\n"
        "BTC,2024-01-01T00:00:00.000Z,42000,42001,,42000.5\n"
        "BTC,2024-01-01T00:00:00.100Z,42008,42010,,42009\n"
        "BTC,2024-01-01T00:00:00.200Z,42004,42006,,42005\n",
        encoding="utf-8",
    )
    config_path.write_text(
        f"""
experiment_name: smoke
output_dir: out
windows:
  - name: macro
    start: "2024-01-01T00:00:00Z"
    end: "2024-01-01T00:00:01Z"
    cme_symbols: ["ZN"]
    crypto_symbols: ["BTC"]
    dataset: "local"
    schema: "csv"
    cme_csv: "{cme_path.name}"
    crypto_csv: "{crypto_path.name}"
""",
        encoding="utf-8",
    )

    summary_path = run_experiment(load_experiment_config(config_path))

    result_path = tmp_path / "out" / "smoke" / "macro" / "ZN__BTC__lead_lag.csv"
    summary = pd.read_csv(summary_path)
    result = pd.read_csv(result_path)
    assert result_path.exists()
    assert summary_path == tmp_path / "out" / "smoke" / "summary.csv"
    row = summary.iloc[0].to_dict()
    assert row["experiment_name"] == "smoke"
    assert row["window_name"] == "macro"
    assert row["cme_symbol"] == "ZN"
    assert row["crypto_symbol"] == "BTC"
    assert row["result_path"] == str(result_path)
    assert row["rows_written"] == len(result)
    assert row["status"] == "success"
    assert pd.isna(row["error_message"])
    assert not result.empty


def test_missing_input_csv_records_failed_status(tmp_path) -> None:
    config_path = tmp_path / "experiment.yaml"
    config_path.write_text(
        """
experiment_name: smoke
output_dir: out
windows:
  - name: macro
    start: "2024-01-01T00:00:00Z"
    end: "2024-01-01T00:00:01Z"
    cme_symbols: ["ZN"]
    crypto_symbols: ["BTC"]
    dataset: "local"
    schema: "csv"
""",
        encoding="utf-8",
    )

    summary_path = run_experiment(load_experiment_config(config_path))

    result_path = tmp_path / "out" / "smoke" / "macro" / "ZN__BTC__lead_lag.csv"
    summary = pd.read_csv(summary_path)
    row = summary.iloc[0].to_dict()
    assert not result_path.exists()
    assert row["status"] == "failed"
    assert row["rows_written"] == 0
    assert row["result_path"] == str(result_path)
    assert "No such file or directory" in row["error_message"]
