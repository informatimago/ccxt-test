from __future__ import annotations
import time, json, math, traceback
import ccxt
import pandas as pd
from datetime import datetime, timedelta, timezone
import yaml
from llm import LLMClient
from paper_broker import PaperBroker
from auth import load_api_credentials

def utc_ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)

def parse_date_utc(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)

def fetch_ohlcv_df(exchange, symbol: str, timeframe: str, since_ms: int, limit: int = None) -> pd.DataFrame:
    data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=limit)
    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df

def build_exchange(cfg):
    ex_name = cfg["exchange"]["name"]
    ex_class = getattr(ccxt, ex_name)
    label = cfg["exchange"].get("auth_label") or None
    creds = load_api_credentials(ex_name, preferred_label=label)
    params = dict(
        apiKey=creds.get("apiKey"),
        secret=creds.get("secret"),
        password=creds.get("password"),
        enableRateLimit=cfg["exchange"].get("enableRateLimit", True)
    )
    return ex_class(params)

def run_live(cfg):
    print("Live Run");
    symbols = cfg["trading"]["symbols"]
    timeframe = cfg["trading"]["timeframe"]
    lookback_days = int(cfg["trading"]["lookback_days"])
    polling_minutes = int(cfg["trading"]["polling_minutes"])
    base_order_size_usd = float(cfg["trading"]["base_order_size_usd"])
    dry_run = bool(cfg["trading"]["dry_run"])

    exchange = build_exchange(cfg)
    exchange.load_markets()
    llm = LLMClient(cfg["llm"])
    paper = PaperBroker(base_cash_usd=10000.0)

    since_dt = datetime.utcnow() - timedelta(days=lookback_days + 5)
    since_ms = utc_ms(since_dt)

    while True:
        try:
            data_by_symbol = {}
            last_prices = {}
            for sym in symbols:
                df = fetch_ohlcv_df(exchange, sym, timeframe, since_ms)
                if df.empty:
                    continue
                data_by_symbol[sym] = df
                last_prices[sym] = float(df["close"].iloc[-1])
            if not data_by_symbol:
                print("No data; sleeping...")
                time.sleep(polling_minutes * 60)
                continue

            decisions = llm.decide(data_by_symbol)
            print("LLM decisions:", decisions.model_dump())

            for asset in decisions.assets:
                sym = asset.symbol
                if sym not in last_prices:
                    continue
                price = last_prices[sym]

                if asset.action == "BUY":
                    if dry_run:
                        paper.market_buy(sym, quote_usd=base_order_size_usd, price=price)
                        print(f"[PAPER] BUY {sym} for ~${base_order_size_usd} at {price}")
                    else:
                        amount = base_order_size_usd / price
                        order = exchange.create_market_buy_order(sym, amount)
                        print("[LIVE] BUY order:", order)

                elif asset.action == "SELL":
                    if dry_run:
                        paper.market_sell_all(sym, price=price)
                        print(f"[PAPER] SELL ALL {sym} at {price}")
                    else:
                        balance = exchange.fetch_free_balance()
                        base_ccy = sym.split("/")[0]
                        amount = float(balance.get(base_ccy, 0.0))
                        if amount > 0:
                            order = exchange.create_market_sell_order(sym, amount)
                            print("[LIVE] SELL order:", order)
                        else:
                            print(f"[LIVE] No {base_ccy} to sell.")

            if dry_run:
                eq = paper.equity(last_prices)
                print(f"[PAPER] Equity: ${eq:,.2f} | Cash: ${paper.portfolio.cash_usd:,.2f} | Positions: { {k:v.size for k,v in paper.portfolio.positions.items()} }")
            else:
                print("[LIVE] Cycle complete.")

        except Exception as e:
            print("Error in live cycle:", e)
            traceback.print_exc()

        time.sleep(polling_minutes * 60)

def run_historic(cfg):
    """
    Historic/backtest mode:
    - Window length = lookback_days.
    - Start at trading.historic_start (inclusive).
    - At step t, decisions use data up to bar t; orders execute at NEXT bar's open.
    - PaperBroker only. Writes backtest_equity.csv.
    """
    print("Historic Run");
    symbols = cfg["trading"]["symbols"]
    timeframe = cfg["trading"]["timeframe"]
    lookback_days = int(cfg["trading"]["lookback_days"])
    base_order_size_usd = float(cfg["trading"]["base_order_size_usd"])

    historic_start_str = (cfg["trading"].get("historic_start") or "").strip()
    if not historic_start_str:
        raise ValueError("historic_start must be set (e.g., 2024-01-01) for historic mode")
    start_dt = parse_date_utc(historic_start_str)

    exchange = build_exchange(cfg)
    exchange.load_markets()
    llm = LLMClient(cfg["llm"])
    paper = PaperBroker(base_cash_usd=10000.0)

    # Fetch from (historic_start - lookback padding) to present
    since_dt = start_dt - timedelta(days=lookback_days + 5)
    since_ms = utc_ms(since_dt)

    dfs = {}
    for sym in symbols:
        df = fetch_ohlcv_df(exchange, sym, timeframe, since_ms)
        if df.empty:
            raise RuntimeError(f"No OHLCV fetched for {sym}.")
        dfs[sym] = df

    min_len = min(len(df) for df in dfs.values())
    # find first index >= start_dt for all symbols
    first_idxs = []
    for sym, df in dfs.items():
        idxs = df.index[df["timestamp"] >= pd.Timestamp(start_dt)]
        if len(idxs) == 0:
            raise RuntimeError(f"No bars at or after {start_dt} for {sym}.")
        first_idxs.append(int(idxs[0]))
    start_idx = max(first_idxs)

    if start_idx < lookback_days:
        raise RuntimeError(f"Not enough lookback history before {historic_start_str}. Choose a later start or increase padding.")

    # iterate until we still have a next bar for execution
    end_idx_exclusive = min_len - 1

    equity_rows = []
    step_count = 0
    for idx in range(start_idx, end_idx_exclusive):
        print(f"Processing date index {idx}")
        data_by_symbol = {}
        next_prices = {}

        if idx + 1 >= min_len:
            break

        for sym, df in dfs.items():
            if idx - (lookback_days - 1) < 0:
                break
            window = df.iloc[idx - (lookback_days - 1): idx + 1].copy()
            data_by_symbol[sym] = window
            next_open = float(df["open"].iloc[idx + 1])
            next_prices[sym] = next_open

        if len(data_by_symbol) != len(symbols):
            continue

        decisions = llm.decide(data_by_symbol)

        for asset in decisions.assets:
            sym = asset.symbol
            price = next_prices.get(sym)
            if price is None or price <= 0:
                continue
            if asset.action == "BUY":
                paper.market_buy(sym, quote_usd=base_order_size_usd, price=price)
            elif asset.action == "SELL":
                paper.market_sell_all(sym, price=price)

        eq = paper.equity(next_prices)
        equity_rows.append({
            "timestamp": dfs[symbols[0]]["timestamp"].iloc[idx + 1],
            "equity": eq,
            "cash": paper.portfolio.cash_usd
        })
        step_count += 1
        if step_count % 20 == 0:
            print(f"[HIST] step {step_count}, equity={eq:.2f} at {equity_rows[-1]['timestamp']}")

    if equity_rows:
        eq_df = pd.DataFrame(equity_rows)
        eq_df.to_csv("backtest_equity.csv", index=False)
        print(f"[HIST] Saved equity curve to backtest_equity.csv ({len(eq_df)} rows).")
    else:
        print("[HIST] No equity rows produced. Check historic_start and lookback_days.")

def main():
    with open("config.yaml", "r") as f:
        cfg = yaml.safe_load(f)

    mode = (cfg["trading"].get("mode") or "live").lower()
    if mode == "historic":
        run_historic(cfg)
    else:
        run_live(cfg)

if __name__ == "__main__":
    main()
