from __future__ import annotations
import numpy as np
from typing import Dict, Any, List

try:
    import talib
except Exception:
    talib = None

def ensure_talib():
    if talib is None:
        raise RuntimeError("TA-Lib is required for talib summaries, but it's not available. Install native TA-Lib and the Python package.")

def _last_valid(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    mask = ~np.isnan(x)
    if not mask.any():
        return float("nan")
    return float(x[mask][-1])

def compact_features(df, pattern_whitelist: List[str] | None = None) -> Dict[str, Any]:
    ensure_talib()
    o,h,l,c,v = [df[k].values.astype(float) for k in ("open","high","low","close","volume")]
    sma20  = talib.SMA(c, timeperiod=20)
    sma50  = talib.SMA(c, timeperiod=50)
    sma200 = talib.SMA(c, timeperiod=200)
    rsi14  = talib.RSI(c, timeperiod=14)
    macd, macds, macdh = talib.MACD(c, 12, 26, 9)
    natr14 = talib.NATR(h, l, c, timeperiod=14)
    up, mid, low = talib.BBANDS(c, timeperiod=20, nbdevup=2, nbdevdn=2)
    bb_pos_b = (c - low) / np.maximum(up - low, 1e-12)
    bb_width = (up - low) / np.maximum(mid, 1e-12) * 100.0
    adx14 = talib.ADX(h, l, c, timeperiod=14)
    vol_sma20 = talib.SMA(v, timeperiod=20)
    vol_ratio20 = v / np.maximum(vol_sma20, 1e-12)
    adosc = talib.ADOSC(h, l, c, v, fastperiod=3, slowperiod=10)
    roc_1 = talib.ROC(c, 1); roc_7 = talib.ROC(c, 7); roc_30 = talib.ROC(c, 30)

    def pct_from(price, ma):
        return 100.0 * (price/ma - 1.0) if not np.isnan(ma) and ma != 0 else float("nan")

    price_last = _last_valid(c)
    features = {
        "roc_1d": _last_valid(roc_1),
        "roc_7d": _last_valid(roc_7),
        "roc_30d": _last_valid(roc_30),
        "pct_from_sma20": pct_from(price_last, _last_valid(sma20)),
        "pct_from_sma200": pct_from(price_last, _last_valid(sma200)),
        "adx_14": _last_valid(adx14),
        "rsi_14": _last_valid(rsi14),
        "macd_hist_12_26_9": _last_valid(macdh),
        "natr_14": _last_valid(natr14),
        "bb_pos_b": _last_valid(bb_pos_b),
        "bb_width": _last_valid(bb_width),
        "vol_ratio_20": _last_valid(vol_ratio20),
        "adosc_3_10": _last_valid(adosc),
    }

    sma20_last, sma50_last = _last_valid(sma20), _last_valid(sma50)
    if not np.isnan(sma20_last) and not np.isnan(sma50_last) and not np.isnan(price_last):
        if sma20_last > sma50_last and price_last > sma20_last:
            features["ma_state"] = "bull"
        elif sma20_last < sma50_last and price_last < sma20_last:
            features["ma_state"] = "bear"
        else:
            features["ma_state"] = "flat"
    else:
        features["ma_state"] = "unknown"

    if pattern_whitelist:
        patt_val = 0.0
        patt_name = ""
        patt_age = None
        last_idx = -1
        for pname in pattern_whitelist:
            func = getattr(talib, pname, None)
            if func is None:
                continue
            arr = func(o,h,l,c)
            idxs = np.where(arr != 0)[0]
            if idxs.size > 0:
                idx = idxs[-1]
                if idx > last_idx:
                    last_idx = idx
                    patt_val = float(arr[idx])
                    patt_name = pname
        if last_idx >= 0:
            patt_age = int(len(df) - 1 - last_idx)
        features["last_pattern"] = patt_name
        features["pattern_sign"] = int(np.sign(patt_val)) if patt_name else 0
        features["pattern_age_days"] = patt_age

    return features

def pair_features(df_a, df_b) -> Dict[str, Any]:
    ensure_talib()
    c_a = df_a["close"].values.astype(float)
    c_b = df_b["close"].values.astype(float)
    n = min(len(c_a), len(c_b))
    c_a = c_a[-n:]; c_b = c_b[-n:]
    ratio = c_a / np.maximum(c_b, 1e-12)

    sma20 = talib.SMA(ratio, timeperiod=20)
    std20 = talib.STDDEV(ratio, timeperiod=20, nbdev=1)
    z = (ratio - sma20) / np.maximum(std20, 1e-12)

    up, mid, low = talib.BBANDS(ratio, timeperiod=20, nbdevup=2, nbdevdn=2)
    bb_pos_b = (ratio - low) / np.maximum(up - low, 1e-12)
    bb_width = (up - low) / np.maximum(mid, 1e-12) * 100.0

    return {
        "ratio_z": _last_valid(z),
        "ratio_bb_pos_b": _last_valid(bb_pos_b),
        "ratio_bb_width": _last_valid(bb_width)
    }
