from __future__ import annotations
import time, json, math, traceback
import ccxt
import yaml
import pandas as pd
from auth import load_api_credentials
from datetime import datetime, timedelta, timezone
from llm import LLMClient
from paper_broker import PaperBroker

def utc_ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)

def fetch_ohlcv_df(exchange, symbol: str, timeframe: str, since_ms: int, limit: int = None) -> pd.DataFrame:
    data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=limit)
    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df


def build_exchange(cfg):
    ex_class = getattr(ccxt, cfg["exchange"]["name"])
    label = cfg["exchange"].get("auth_label") or None
    creds = load_api_credentials(cfg["exchange"]["name"], preferred_label=label)
    return ex_class({
            "apiKey": creds.get("apiKey"),
            "secret": creds.get("secret"),
            "password": creds.get("password"),
            "enableRateLimit": True
          })


def main():
    with open("config.yaml", "r") as f:
        cfg = yaml.safe_load(f)

    symbols = cfg["trading"]["symbols"]
    timeframe = cfg["trading"]["timeframe"]
    lookback_days = int(cfg["trading"]["lookback_days"])
    polling_minutes = int(cfg["trading"]["polling_minutes"])
    base_order_size_usd = float(cfg["trading"]["base_order_size_usd"])
    dry_run = bool(cfg["trading"]["dry_run"])
    max_positions_per_symbol = int(cfg["trading"]["max_positions_per_symbol"])

    # Exchange
    exchange = build_exchange(cfg)
    exchange.load_markets()

    # LLM
    llm = LLMClient(cfg["llm"])

    # Paper broker
    paper = PaperBroker(base_cash_usd=10000.0)

    since_dt = datetime.utcnow() - timedelta(days=lookback_days + 5)  # pad a bit
    since_ms = utc_ms(since_dt)

    while True:
        try:
            # 1) Pull data
            print(f"Pull data {timeframe}");
            data_by_symbol = {}
            last_prices = {}
            for sym in symbols:
                df = fetch_ohlcv_df(exchange, sym, timeframe, since_ms)
                if df.empty:
                    continue
                data_by_symbol[sym] = df
                last_prices[sym] = float(df["close"].iloc[-1])

            if not data_by_symbol:
                print("No data fetched; sleeping...")
                time.sleep(polling_minutes * 60)
                continue

            # 2) Call LLM for decisions
            decisions = llm.decide(data_by_symbol)
            print("LLM decisions:", decisions.model_dump())

            # 3) Map asset decisions to (paper) orders
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
                        # LIVE: simple market buy by quote size (approximate by base size at current price)
                        amount = base_order_size_usd / price
                        order = exchange.create_market_buy_order(sym, amount)
                        print("[LIVE] BUY order:", order)

                elif asset.action == "SELL":
                    if dry_run:
                        paper.market_sell_all(sym, price=price)
                        print(f"[PAPER] SELL ALL {sym} at {price}")
                    else:
                        # LIVE: sell all (requires fetching position/balance; spot-only approximation)
                        balance = exchange.fetch_free_balance()
                        base_ccy = sym.split("/")[0]
                        amount = float(balance.get(base_ccy, 0.0))
                        if amount > 0:
                            order = exchange.create_market_sell_order(sym, amount)
                            print("[LIVE] SELL order:", order)
                        else:
                            print(f"[LIVE] No {base_ccy} to sell.")

            # 4) Display equity (paper) / simple log (live)
            if dry_run:
                eq = paper.equity(last_prices)
                print(f"[PAPER] Equity: ${eq:,.2f} | Cash: ${paper.portfolio.cash_usd:,.2f} | Positions: { {k:v.size for k,v in paper.portfolio.positions.items()} }")
            else:
                print("[LIVE] Cycle complete.")

        except Exception as e:
            print("Error in cycle:", e)
            traceback.print_exc()

        # 5) Sleep until next cycle
        time.sleep(polling_minutes * 60)

if __name__ == "__main__":
    main()
