# Project Instructions

- Always use `..venv\Scripts\python.exe`; never use `..\venv\Scripts\python.exe`.
- Run tests with `..venv\Scripts\python.exe -m pytest`.
- The local data root is `E:\QuantData\yield-lag`.
- Never commit `.env`, CSV data files, SQL backups, API keys, or other secrets.
- Live trading is forbidden.
- Private APIs and order placement are forbidden.
- The `DATABENTO_API_KEY` must only come from an environment variable.
- Use `--dry-run` and `--reuse-existing` before any Databento download.
- Do not use `--allow-large-cme-download` unless explicitly instructed.
