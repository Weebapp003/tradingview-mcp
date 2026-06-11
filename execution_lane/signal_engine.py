# -*- coding: utf-8 -*-
"""
Phase 2 — Auto signal generator.

Replaces manual --bias with a scored multi-factor signal:

  Price action (4 factors):  RSI-14, VWAP, EMA9/EMA21 cross, 3-bar trend
  Chain     (4 factors):     PCR, OI flow, IV skew, max-pain gravity

Score range: -8 to +8
  <= -3  →  SHORT   conviction = min(10, |score| * 1.25)
  >= +3  →  LONG    conviction = min(10,  score  * 1.25)
  else   →  NEUTRAL conviction = 0
"""
import json
from datetime import datetime, date, timedelta

from config import MCX_EXCHANGE, LOG_DIR


# ── Candle fetching ───────────────────────────────────────────────────────────

def fetch_candles(obj, token: str, interval: str = "FIFTEEN_MINUTE", n_bars: int = 50) -> list:
    """Fetch recent OHLCV bars from SmartAPI. Returns list of bar dicts."""
    now     = datetime.now()
    from_dt = now - timedelta(minutes=15 * n_bars + 120)
    params  = {
        "exchange":    MCX_EXCHANGE,
        "symboltoken": token,
        "interval":    interval,
        "fromdate":    from_dt.strftime("%Y-%m-%d %H:%M"),
        "todate":      now.strftime("%Y-%m-%d %H:%M"),
    }
    try:
        resp = obj.getCandleData(params)
    except Exception:
        return []
    if not resp or not resp.get("data"):
        return []
    bars = []
    for row in resp["data"][-n_bars:]:
        try:
            bars.append({
                "ts":     row[0],
                "open":   float(row[1]),
                "high":   float(row[2]),
                "low":    float(row[3]),
                "close":  float(row[4]),
                "volume": float(row[5]),
            })
        except (IndexError, TypeError, ValueError):
            continue
    return bars


# ── Indicators ────────────────────────────────────────────────────────────────

def _vwap(bars: list) -> float:
    """Session VWAP — uses today's bars only, falls back to last 20."""
    today   = date.today().isoformat()
    session = [b for b in bars if str(b["ts"])[:10] == today] or bars[-20:]
    num = sum(((b["high"] + b["low"] + b["close"]) / 3) * b["volume"] for b in session)
    den = sum(b["volume"] for b in session)
    return num / den if den else 0.0


def _rsi(closes: list, period: int = 14) -> float:
    """Wilder RSI. Returns 50.0 if insufficient data."""
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_g / avg_l)), 2)


def _ema(closes: list, period: int) -> float:
    """Exponential moving average of closes list."""
    if not closes:
        return 0.0
    k, ema = 2 / (period + 1), closes[0]
    for c in closes[1:]:
        ema = c * k + ema * (1 - k)
    return round(ema, 2)


# ── Price-action scoring ──────────────────────────────────────────────────────

def _score_price_action(bars: list, underlying: float) -> dict:
    if len(bars) < 20:
        return {"score": 0, "factors": {}, "rsi": 50.0, "vwap": 0.0, "vol_confirm": False}

    closes  = [b["close"]  for b in bars]
    volumes = [b["volume"] for b in bars]

    rsi   = _rsi(closes)
    vwap  = _vwap(bars)
    ema9  = _ema(closes, 9)
    ema21 = _ema(closes, 21)
    avg_v = sum(volumes[-20:]) / 20

    rsi_score   = 1 if rsi > 55 else (-1 if rsi < 45 else 0)
    vwap_score  = 1 if underlying > vwap  else -1
    ema_score   = 1 if ema9 > ema21       else -1

    # 3-bar trend: majority up closes = +1, majority down = -1
    last3 = closes[-3:]
    up    = sum(1 for i in range(1, len(last3)) if last3[i] > last3[i - 1])
    trend_score = 1 if up >= 2 else (-1 if up == 0 else 0)

    return {
        "score": rsi_score + vwap_score + ema_score + trend_score,
        "factors": {
            "rsi":       {"score": rsi_score,   "label": f"RSI {rsi:.1f}"},
            "vwap":      {"score": vwap_score,  "label": f"Price {'>' if vwap_score > 0 else '<'} VWAP {vwap:.0f}"},
            "ema_cross": {"score": ema_score,   "label": f"EMA9 {ema9:.0f} {'>' if ema_score > 0 else '<='} EMA21 {ema21:.0f}"},
            "bar_trend": {"score": trend_score, "label": f"{up}/2 up bars in last 3"},
        },
        "rsi":         rsi,
        "vwap":        vwap,
        "vol_confirm": volumes[-1] > avg_v if avg_v else False,
    }


# ── Chain scoring ─────────────────────────────────────────────────────────────

def _score_chain(analysis: dict) -> dict:
    pcr        = analysis.get("pcr_full", 1.0)
    oi_lean    = analysis.get("oi_chg", {}).get("net_lean", "mixed")
    skew       = analysis.get("skew") or {}
    max_pain   = analysis.get("max_pain", 0.0)
    underlying = analysis.get("underlying", 0.0)
    mp_gap     = max_pain - underlying

    pcr_score  = -1 if pcr > 1.3 else (1 if pcr < 0.7 else 0)
    oi_score   = 1 if oi_lean == "bullish" else (-1 if oi_lean == "bearish" else 0)
    skew_lean  = skew.get("lean", "")
    skew_score = -1 if "put-skew" in skew_lean else (1 if "call-skew" in skew_lean else 0)
    mp_score   = 1 if mp_gap > 100 else (-1 if mp_gap < -100 else 0)

    return {
        "score": pcr_score + oi_score + skew_score + mp_score,
        "factors": {
            "pcr":      {"score": pcr_score,  "label": f"PCR {pcr:.3f}"},
            "oi_flow":  {"score": oi_score,   "label": f"OI flow {oi_lean}"},
            "iv_skew":  {"score": skew_score, "label": f"IV {skew_lean or 'neutral'}"},
            "max_pain": {"score": mp_score,   "label": f"Max pain {max_pain:.0f} ({mp_gap:+.0f} vs spot)"},
        },
    }


# ── Signal log ────────────────────────────────────────────────────────────────

_SIGNAL_LOG = LOG_DIR / f"signals_{date.today():%Y%m%d}.jsonl"


def _log(signal: dict):
    LOG_DIR.mkdir(exist_ok=True)
    with open(_SIGNAL_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({**signal, "ts": datetime.now().isoformat()}) + "\n")


# ── Public entry point ────────────────────────────────────────────────────────

def generate(obj, futures_token: str, analysis: dict) -> dict:
    """
    Generate a trading signal combining price action + chain analysis.

    Returns:
      bias:        "long" | "short" | "neutral"
      conviction:  0-10
      score:       -8 to +8
      pa_score:    price-action component (-4 to +4)
      ch_score:    chain component (-4 to +4)
      pa_factors:  dict of factor breakdowns
      ch_factors:  dict of factor breakdowns
      vol_confirm: bool — volume above 20-bar average
      underlying:  float
      rsi:         float
      vwap:        float
      auto_stop:   float — suggested underlying stop level
      auto_targets: list[float]
    """
    underlying = analysis.get("underlying", 0.0)

    bars = fetch_candles(obj, futures_token, interval="FIFTEEN_MINUTE", n_bars=50)
    pa   = _score_price_action(bars, underlying)
    ch   = _score_chain(analysis)

    total = pa["score"] + ch["score"]

    if total <= -3:
        bias       = "short"
        conviction = min(10, int(abs(total) * 1.25))
        auto_stop  = round(underlying * 1.015, 0)   # 1.5% above for short stop
        auto_targets = [round(underlying * 0.975, 0), round(underlying * 0.950, 0)]
    elif total >= 3:
        bias       = "long"
        conviction = min(10, int(total * 1.25))
        auto_stop  = round(underlying * 0.985, 0)   # 1.5% below for long stop
        auto_targets = [round(underlying * 1.025, 0), round(underlying * 1.050, 0)]
    else:
        bias         = "neutral"
        conviction   = 0
        auto_stop    = 0.0
        auto_targets = []

    # Tighten conviction if volume doesn't confirm
    if bias != "neutral" and not pa.get("vol_confirm"):
        conviction = max(1, conviction - 1)

    signal = {
        "bias":         bias,
        "conviction":   conviction,
        "score":        total,
        "pa_score":     pa["score"],
        "ch_score":     ch["score"],
        "pa_factors":   pa["factors"],
        "ch_factors":   ch["factors"],
        "vol_confirm":  pa.get("vol_confirm", False),
        "underlying":   underlying,
        "rsi":          pa.get("rsi"),
        "vwap":         pa.get("vwap"),
        "auto_stop":    auto_stop,
        "auto_targets": auto_targets,
    }

    _log(signal)
    return signal
