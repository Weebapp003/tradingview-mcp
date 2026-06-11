# -*- coding: utf-8 -*-
"""
Online learner: perceptron-style weight updates from closed trade outcomes.

Each of the 8 signal factors starts with weight 1.0.
After every closed trade:
  WIN  + factor agreed with trade direction  ->  weight += LEARN_RATE
  WIN  + factor opposed trade direction      ->  no change
  LOSS + factor agreed with trade direction  ->  weight -= LEARN_RATE  (punish)
  LOSS + factor opposed trade direction      ->  weight += LEARN_RATE * 0.5 (reward dissent)

Weights clamped to [MIN_W, MAX_W].
The stronger a factor's predictive record, the more it moves the signal.
Noise factors naturally drift toward MIN_W over time.
"""
import json
from config import LOG_DIR

WEIGHTS_FILE = LOG_DIR / "weights.json"
LEARN_RATE   = 0.1
MIN_W        = 0.1
MAX_W        = 3.0

FACTOR_KEYS = [
    "rsi", "vwap", "ema_cross", "bar_trend",   # price-action
    "pcr", "oi_flow", "iv_skew", "max_pain",    # chain
]


def load_weights() -> dict:
    if WEIGHTS_FILE.exists():
        try:
            data = json.loads(WEIGHTS_FILE.read_text())
            for k in FACTOR_KEYS:
                data.setdefault(k, 1.0)
            return data
        except Exception:
            pass
    return _default()


def _default() -> dict:
    w = {k: 1.0 for k in FACTOR_KEYS}
    w.update({"trades_seen": 0, "wins": 0, "losses": 0, "win_rate": 0.0})
    return w


def save_weights(w: dict):
    WEIGHTS_FILE.write_text(json.dumps(w, indent=2))


def update(closed_trade: dict) -> dict:
    """
    Update weights from a single closed trade.
    Returns the updated weights dict.
    """
    outcome = closed_trade.get("outcome")
    if outcome not in ("WIN", "LOSS"):
        return load_weights()

    entry_signal = closed_trade.get("entry_signal")
    if not entry_signal:
        # No signal stored — can't learn from this trade, just update counts
        w = load_weights()
        w["trades_seen"] = w.get("trades_seen", 0) + 1
        if outcome == "WIN":
            w["wins"] = w.get("wins", 0) + 1
        else:
            w["losses"] = w.get("losses", 0) + 1
        seen = w["trades_seen"]
        w["win_rate"] = round(w["wins"] / seen, 3) if seen else 0.0
        save_weights(w)
        return w

    w         = load_weights()
    bias      = closed_trade.get("bias", "long")
    direction = 1 if bias == "long" else -1

    pa = entry_signal.get("pa_factors", {})
    ch = entry_signal.get("ch_factors", {})
    all_factors = {**pa, **ch}

    for key in FACTOR_KEYS:
        factor_score = all_factors.get(key, {}).get("score", 0)
        if factor_score == 0:
            continue

        agreed = (factor_score * direction) > 0

        if outcome == "WIN":
            if agreed:
                w[key] = round(min(MAX_W, w[key] + LEARN_RATE), 3)
            # opposed but won: no change (lucky — don't reward noise)
        else:  # LOSS
            if agreed:
                w[key] = round(max(MIN_W, w[key] - LEARN_RATE), 3)
            else:
                # factor was against our direction and we lost — it was right
                w[key] = round(min(MAX_W, w[key] + LEARN_RATE * 0.5), 3)

    w["trades_seen"] = w.get("trades_seen", 0) + 1
    if outcome == "WIN":
        w["wins"]   = w.get("wins", 0) + 1
    else:
        w["losses"] = w.get("losses", 0) + 1
    seen = w["trades_seen"]
    w["win_rate"] = round(w["wins"] / seen, 3) if seen else 0.0

    save_weights(w)
    return w


def print_weights(w: dict):
    """Pretty-print current weights for the scheduler display."""
    seen = w.get("trades_seen", 0)
    wins = w.get("wins", 0)
    wr   = w.get("win_rate", 0.0)
    print(f"  [WEIGHTS]  trades={seen}  wins={wins}  win_rate={wr:.1%}")
    for k in FACTOR_KEYS:
        bar = int(w.get(k, 1.0) * 10)
        print(f"    {k:<12} {w.get(k,1.0):.2f}  {'|' * bar}")
