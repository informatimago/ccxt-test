from __future__ import annotations
import json
from typing import Dict, Any, List
from pydantic import BaseModel, Field, ValidationError
from llama_cpp import Llama

class AssetDecision(BaseModel):
    symbol: str
    action: str = Field(description="One of BUY, SELL, HOLD")
    confidence: float = Field(ge=0.0, le=1.0, description="0..1 confidence")
    comment: str = ""

class PairDecision(BaseModel):
    pair: str = Field(description="Like 'BTC/USDT vs ETH/USDT'")
    action: str = Field(description="One of LONG_SPREAD, SHORT_SPREAD, NO_TRADE")
    confidence: float = Field(ge=0.0, le=1.0)
    comment: str = ""

class LLMResponse(BaseModel):
    assets: List[AssetDecision]
    pairs: List[PairDecision]

SYSTEM_PROMPT = """You are a careful quantitative trading assistant.
You are given recent OHLCV summaries (daily) for a set of crypto symbols (vs USDT).
Your task:
1) Output one decision per symbol: BUY, SELL or HOLD with confidence 0..1.
2) Output pair-trade suggestions for each symbol pair among the given set:
   action in {LONG_SPREAD, SHORT_SPREAD, NO_TRADE}.
   - LONG_SPREAD means: be long the first, short the second.
   - SHORT_SPREAD means: be short the first, long the second.
3) Keep a conservative bias. Prefer HOLD or NO_TRADE when uncertain.
4) STRICTLY RETURN VALID JSON ONLY. No commentary outside JSON.
"""

USER_PROMPT_TEMPLATE = """Symbols: {symbols}

Data summary (per symbol):
{summaries}

Constraints:
- Only use the information above.
- Do not assume future info.
- Output must be a single JSON object with two keys: "assets" and "pairs".
JSON Schema (informal):
{{
  "assets":[{{"symbol": "BTC/USDT", "action":"BUY|SELL|HOLD", "confidence":0.0..1.0, "comment":""}}, ...],
  "pairs":[{{"pair":"BTC/USDT vs ETH/USDT", "action":"LONG_SPREAD|SHORT_SPREAD|NO_TRADE", "confidence":0.0..1.0, "comment":""}}, ...]
}}
"""

def format_summary(symbol: str, df) -> str:
    """Compact textual summary of OHLCV daily data for prompting."""
    # df expected columns: timestamp, open, high, low, close, volume
    # We keep last 60 rows for brevity
    tail = df.tail(60)
    closes = [round(float(x), 6) for x in tail["close"].tolist()]
    vols = [round(float(x), 6) for x in tail["volume"].tolist()]
    return f"- {symbol}: last_closes={closes}\\n  last_volumes={vols}"

class LLMClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.llm = Llama(
            model_path=cfg["model_path"],
            n_ctx=cfg.get("n_ctx", 4096),
            n_threads=cfg.get("n_threads", 6),
            verbose=False
        )
        self.gen_kwargs = dict(
            temperature=cfg.get("temperature", 0.3),
            top_p=cfg.get("top_p", 0.9),
            max_tokens=1024,
            stop=[]
        )

    def decide(self, data_by_symbol: Dict[str, Any]) -> LLMResponse:
        symbols = list(data_by_symbol.keys())
        summaries = "\n".join(format_summary(sym, df) for sym, df in data_by_symbol.items())
        user_prompt = USER_PROMPT_TEMPLATE.format(symbols=", ".join(symbols), summaries=summaries)

        messages = [
            {"role":"system", "content": SYSTEM_PROMPT},
            {"role":"user", "content": user_prompt}
        ]

        # llama_cpp chat completion
        out = self.llm.create_chat_completion(messages=messages, **self.gen_kwargs)
        content = out["choices"][0]["message"]["content"].strip()
        # Defensive: sometimes models wrap code fences
        if content.startswith("```"):
            content = content.strip("`")
            # remove potential "json" header line
            content = "\n".join([ln for ln in content.splitlines() if not ln.strip().lower().startswith("json")])

        try:
            data = json.loads(content)
            return LLMResponse(**data)
        except (json.JSONDecodeError, ValidationError) as e:
            # Fallback to HOLD/NO_TRADE on failure
            assets = [AssetDecision(symbol=s, action="HOLD", confidence=0.0, comment="LLM parse error fallback") for s in symbols]
            pairs = []
            for i in range(len(symbols)):
                for j in range(i+1, len(symbols)):
                    pair = f"{symbols[i]} vs {symbols[j]}"
                    pairs.append(PairDecision(pair=pair, action="NO_TRADE", confidence=0.0, comment="LLM parse error fallback"))
            return LLMResponse(assets=assets, pairs=pairs)
