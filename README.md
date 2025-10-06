# CCXT + Local LLaMA Crypto Trading Agent (Paper-Trading by default)

This is a minimal **Python** template that:
- Uses **CCXT** to fetch OHLCV for a few cryptos (default: BTC, ETH, DOGE vs USDT).
- Summarizes the last 6 months of daily data.
- Asks a **local LLaMA model** (via `llama-cpp-python`) for **buy/sell/hold** signals per asset **and** pair-trade suggestions (e.g., long BTC / short ETH).
- Executes **paper trades** by default (simulated portfolio). You can enable real trading (at your own risk) by setting `dry_run: false` and providing API keys.

> ⚠️ **Disclaimer**: This code is for educational purposes only. Crypto trading is risky. Past performance is not indicative of future results. You are responsible for any use and losses.

## Quick start

1. **Python env**
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. **Download a local LLaMA GGUF model**
- Example (7B instruction-tuned): `TheBloke/Llama-2-7B-Chat-GGUF` or any small instruct model in **GGUF** format.
- Put the file path into `config.yaml` under `llm.model_path`.

3. **Configure**
Edit `config.yaml`:
- `symbols`: default `["BTC/USDT", "ETH/USDT", "DOGE/USDT"]`
- `exchange`: default `binance`
- `dry_run`: `true` (paper) by default
- Add your API keys **only** if you want live trading

### 🔐 Credentials from `~/.apikeys`

Create a file at `~/.apikeys` (or `~/.config/apikeys`) with whitespace key–value pairs per line:

```
# name <ccxt-exchange-id> label <label> apikey <KEY> secret <SECRET> password <PASS-or-empty>
name binance label prod  apikey ABC123 secret XYZ456 password ""
name binance label paper apikey ABC789 secret XYZ999 password ""
name kraken  label prod  apikey KRAKEY secret KRASEC password KRA_PW
```

Then select which to use via `config.yaml`:

```yaml
exchange:
  name: binance
  auth_label: "prod"   # or "paper"; if empty, match by name
```

> Set file permissions: `chmod 600 ~/.apikeys`.

4. **Run**
```bash
python agent.py
```

By default it:
- Pulls ~6 months of *daily* OHLCV for each symbol
- Prompts the LLM to output **strict JSON**
- Parses decisions and either **paper-trades** or places **real market orders** on the configured exchange.
- Sleeps and repeats per `polling_minutes`.

## Files

- `agent.py` — main loop (data fetch → LLM → signals → (paper) orders).
- `llm.py` — wrapper around `llama_cpp` + prompt & JSON schema.
- `paper_broker.py` — simple in-memory portfolio & trade fills for dry-run.
- `config.yaml` — settings (symbols, exchange, timeframe, polling).
- `requirements.txt` — dependencies.

## Notes

- WebSockets, real-time latencies, slippage modeling, and robust risk controls are out of scope for this tiny template.
- For production, add: position sizing rules, PnL tracking, risk limits, persistence (DB), retry & rate-limit handling, and a better prompt calibration.
