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
You are given either raw OHLCV summaries (daily) or compact TA-Lib feature summaries
for a set of crypto symbols (vs USDT). Your task:
1) Output one decision per symbol: BUY, SELL or HOLD with confidence 0..1.
2) Output pair-trade suggestions for each symbol pair among the given set:
   action in {LONG_SPREAD, SHORT_SPREAD, NO_TRADE}.
   - LONG_SPREAD means: be long the first, short the second.
   - SHORT_SPREAD means: be short the first, long the second.
3) Keep a conservative bias. Prefer HOLD or NO_TRADE when uncertain.
4) STRICTLY RETURN VALID JSON ONLY. No commentary outside JSON.
"""

USER_PROMPT_RAW = """Symbols: {symbols}

Raw summaries (per symbol):
{summaries}

Constraints:
- Only use the information above.
- Do not assume future info.
- Output must be a single JSON object with two keys: "assets" and "pairs".
"""

USER_PROMPT_TALIB = """Symbols: {symbols}

Compact TA-Lib features (per symbol):
{summaries}
{pair_summaries}

Constraints:
- Only use the information above.
- Do not assume future info.
- Output must be a single JSON object with two keys: "assets" and "pairs".
"""

def format_raw_summary(symbol: str, df) -> str:
    tail = df.tail(60)
    closes = [round(float(x), 6) for x in tail["close"].tolist()]
    vols = [round(float(x), 6) for x in tail["volume"].tolist()]
    return f"- {symbol}: last_closes={closes}\\n  last_volumes={vols}"

def format_talib_summary(symbol: str, feats: Dict[str, Any]) -> str:
    keys = ["roc_1d","roc_7d","roc_30d","pct_from_sma20","pct_from_sma200","adx_14","ma_state",
            "rsi_14","macd_hist_12_26_9","natr_14","bb_pos_b","bb_width","vol_ratio_20","adosc_3_10",
            "last_pattern","pattern_sign","pattern_age_days"]
    pairs = [f"{k}={feats.get(k)}" for k in keys if k in feats]
    return f"- {symbol}: " + ", ".join(pairs)

def format_pair_summary(pair: str, feats: Dict[str, Any]) -> str:
    keys = ["ratio_z","ratio_bb_pos_b","ratio_bb_width"]
    items = [f"{k}={feats.get(k)}" for k in keys if k in feats]
    return f"- Pair {pair}: " + ", ".join(items)

class LLMClient:
    def __init__(self, cfg_llm: Dict[str, Any], input_mode: str = "raw"):
        self.llm = Llama(
            model_path=cfg_llm["model_path"],
            n_ctx=cfg_llm.get("n_ctx", 4096),
            n_threads=cfg_llm.get("n_threads", 6),
            verbose=False
        )
        self.gen_kwargs = dict(
            temperature=cfg_llm.get("temperature", 0.3),
            top_p=cfg_llm.get("top_p", 0.9),
            max_tokens=1024,
            stop=[]
        )
        self.input_mode = input_mode

    def decide(self, data_by_symbol: Dict[str, Any], pair_text: str = "") -> LLMResponse:
        symbols = list(data_by_symbol.keys())

        if self.input_mode == "talib":
            summaries = "\\n".join(
                format_talib_summary(sym, feats) for sym, feats in data_by_symbol.items()
            )
            user_prompt = USER_PROMPT_TALIB.format(
                symbols=", ".join(symbols),
                summaries=summaries,
                pair_summaries=(f"\\nPair features:\\n{pair_text}" if pair_text else "")
            )
        else:
            summaries = "\\n".join(format_raw_summary(sym, df) for sym, df in data_by_symbol.items())
            user_prompt = USER_PROMPT_RAW.format(symbols=", ".join(symbols), summaries=summaries)

        messages = [
            {"role":"system", "content": SYSTEM_PROMPT},
            {"role":"user", "content": user_prompt}
        ]

        out = self.llm.create_chat_completion(messages=messages, **self.gen_kwargs)
        content = out["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.strip("`")
            content = "\\n".join([ln for ln in content.splitlines() if not ln.strip().lower().startswith("json")])

        try:
            data = json.loads(content)
            return LLMResponse(**data)
        except (json.JSONDecodeError, ValidationError):
            assets = [AssetDecision(symbol=s, action="HOLD", confidence=0.0, comment="LLM parse error fallback") for s in symbols]
            pairs = []
            for i in range(len(symbols)):
                for j in range(i+1, len(symbols)):
                    pair = f"{symbols[i]} vs {symbols[j]}"
                    pairs.append(PairDecision(pair=pair, action="NO_TRADE", confidence=0.0, comment="LLM parse error fallback"))
            return LLMResponse(assets=assets, pairs=pairs)
