from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List
import time

@dataclass
class Position:
    symbol: str
    size: float = 0.0
    avg_price: float = 0.0

@dataclass
class Fill:
    ts: float
    symbol: str
    side: str  # buy/sell
    size: float
    price: float
    value_usd: float

@dataclass
class Portfolio:
    cash_usd: float = 10000.0
    positions: Dict[str, Position] = field(default_factory=dict)
    fills: List[Fill] = field(default_factory=list)

    def mark_to_market(self, prices: Dict[str, float]) -> float:
        equity = self.cash_usd
        for pos in self.positions.values():
            px = prices.get(pos.symbol, pos.avg_price)
            equity += pos.size * px
        return equity

    def _apply_fill(self, symbol: str, side: str, size: float, price: float):
        value = size * price
        if side == "buy":
            self.cash_usd -= value
            pos = self.positions.get(symbol, Position(symbol=symbol, size=0.0, avg_price=0.0))
            new_size = pos.size + size
            pos.avg_price = (pos.size * pos.avg_price + value) / new_size if new_size != 0 else price
            pos.size = new_size
            self.positions[symbol] = pos
        else:
            self.cash_usd += value
            pos = self.positions.get(symbol, Position(symbol=symbol, size=0.0, avg_price=0.0))
            pos.size -= size
            if pos.size <= 1e-12:
                self.positions.pop(symbol, None)
            else:
                self.positions[symbol] = pos

        self.fills.append(Fill(ts=time.time(), symbol=symbol, side=side, size=size, price=price, value_usd=value))

class PaperBroker:
    def __init__(self, base_cash_usd: float = 10000.0):
        self.portfolio = Portfolio(cash_usd=base_cash_usd)

    def market_buy(self, symbol: str, quote_usd: float, price: float):
        size = quote_usd / price if price > 0 else 0.0
        if size <= 0:
            return
        self.portfolio._apply_fill(symbol, "buy", size, price)

    def market_sell_all(self, symbol: str, price: float):
        pos = self.portfolio.positions.get(symbol)
        if not pos or pos.size <= 0:
            return
        self.portfolio._apply_fill(symbol, "sell", pos.size, price)

    def equity(self, prices: dict) -> float:
        return self.portfolio.mark_to_market(prices)
