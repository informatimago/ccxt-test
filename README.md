# CCXT + Local LLaMA Crypto Trading Agent (Live & Historic)

Minimal **Python** template that:
- Uses **CCXT** to fetch OHLCV (default: `BTC/USDT`, `ETH/USDT`, `DOGE/USDT`).
- Summarizes the last `lookback_days` of daily data.
- Asks a **local LLaMA (GGUF via `llama-cpp-python`)** for **BUY/SELL/HOLD** per asset + pair-trade ideas.
- **Live mode**: paper-trades by default; can place real orders if you set `dry_run: false` and provide API keys.
- **Historic mode**: runs a **moving-window backtest** starting at `trading.historic_start` and executes at **next bar's open**. Outputs `backtest_equity.csv`.

> ⚠️ **Disclaimer**: Educational only. Trading risk is yours.

## Quick start

1) Python env
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2) Get a **GGUF** model (e.g., LLaMA-2-7B-Chat Q4_K_M), set path in `config.yaml → llm.model_path`.

3) API keys are loaded from `~/.apikeys`:
```
# name <ccxt-id> label <label> apikey <KEY> secret <SECRET> password <PASS-or-"">
name binance label prod  apikey ABC123 secret XYZ456 password ""
name binance label paper apikey ABC789 secret XYZ999 password ""
name kraken  label prod  apikey KRAKEY secret KRASEC password KRA_PW
```
Select via `exchange.auth_label`. File perms: `chmod 600 ~/.apikeys`.

4) Configure `config.yaml` (see below) and run:
```bash
python agent.py
```

## Modes

### Live mode
- `trading.mode: "live"` (default).
- Pulls latest OHLCV, queries LLM, and either **paper-trades** or (if `dry_run: false`) places real **market** orders via CCXT.

### Historic/backtest mode
- `trading.mode: "historic"` with `trading.historic_start: "YYYY-MM-DD"`.
- Uses a **moving window** of `lookback_days` bars.
- At each step *t*, LLM sees bars up to *t*; orders are executed at **next bar's open**.
- Uses paper broker only and writes `backtest_equity.csv` (`timestamp,equity,cash`).

## Files

- `agent.py` — live loop + historic backtest.
- `llm.py` — llama.cpp wrapper and strict JSON parsing with Pydantic.
- `paper_broker.py` — tiny in-memory portfolio and fills.
- `auth.py` — loads keys from `~/.apikeys` (or `~/.config/apikeys`).
- `config.yaml` — settings.
- `requirements.txt` — deps.
