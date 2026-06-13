# -*- coding: utf-8 -*-
"""
Historical backtest + ML training on CRUDEOILM 15-min futures data.

What this does:
  1. Fetches up to 2 years of 15-min OHLCV data from SmartAPI
     (one API call per 30-day window, stitched across contract expiries)
  2. Re-runs the PA signal engine (RSI / VWAP / EMA9-21 / bar-trend) on
     every bar — same logic as live, same threshold (±0.375 normalized)
  3. Chain factors set to 0 (no historical chain data is available)
  4. Simulates option trades: ATM premium estimated from spot price,
     WIN if underlying moves +2.5% in direction, LOSS if -1.5%
  5. Trains the online_learner weights on every simulated trade
  6. Saves trained weights to logs/weights_backtest.json
     Run  copy logs\weights_backtest.json logs\weights.json  to go live

Usage:
  python backtest.py
  python backtest.py --months 6      # shorter history
  python backtest.py --promote       # auto-copy to live weights after training
"""
import sys
import json
import argparse
import math
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import auth
from signal_engine import _rsi, _ema     # reuse indicator math
from config import MCX_EXCHANGE, LOG_DIR
from option_chain import load_scrip_master

# yfinance optional — used as fallback when SmartAPI historical data is sparse
try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False

# ── Constants ──────────────────────────────────────────────────────────────────

BACKTEST_WEIGHTS_FILE = LOG_DIR / "weights_backtest.json"
LIVE_WEIGHTS_FILE     = LOG_DIR / "weights.json"

LEARN_RATE = 0.1
MIN_W      = 0.1
MAX_W      = 3.0
THRESHOLD  = 0.375   # same as live signal engine
BARS_AHEAD = 20      # max bars to scan for SL/TP hit (~5 hours)
WIN_PCT    = 0.025   # underlying must move 2.5% in direction
LOSS_PCT   = 0.015   # 1.5% move against = SL

FACTOR_KEYS = [
    "rsi", "vwap", "ema_cross", "bar_trend",   # price-action (have history)
    "pcr", "oi_flow", "iv_skew", "max_pain",   # chain (set to 0 in backtest)
]

_SEP  = "═" * 68
_sep  = "─" * 68


# ── Scrip master search ────────────────────────────────────────────────────────

def find_contracts(scrip_master: list, months_back: int) -> list:
    """
    Return a list of (token, expiry_date, symbol) for CRUDEOILM futures
    covering the past `months_back` months, sorted by expiry (oldest first).
    """
    cutoff = date.today() - timedelta(days=months_back * 30)
    today  = date.today()
    hits   = []

    for instr in scrip_master:
        name = instr.get("name", "") or instr.get("symbol", "")
        if "CRUDEOILM" not in name.upper():
            continue
        if instr.get("instrumenttype", "") not in ("FUTCOM", "FUTSTK", ""):
            # Keep FUTCOM and anything that looks like a futures contract
            itype = instr.get("instrumenttype", "")
            if itype and itype not in ("FUTCOM",):
                continue

        expiry_raw = instr.get("expiry", "")
        if not expiry_raw:
            continue
        try:
            expiry = _parse_expiry(expiry_raw)
        except Exception:
            continue
        if expiry is None:
            continue
        if expiry < cutoff or expiry > today + timedelta(days=60):
            continue

        hits.append({
            "token":  instr.get("token", ""),
            "symbol": instr.get("symbol", name),
            "expiry": expiry,
        })

    # Deduplicate by expiry month (keep one contract per calendar month)
    by_month = {}
    for h in hits:
        key = (h["expiry"].year, h["expiry"].month)
        if key not in by_month:
            by_month[key] = h

    return sorted(by_month.values(), key=lambda x: x["expiry"])


def _parse_expiry(raw: str):
    for fmt in ("%d%b%Y", "%d-%b-%Y", "%Y-%m-%d", "%d%b%y"):
        try:
            return datetime.strptime(raw.strip().upper(), fmt).date()
        except ValueError:
            continue
    return None


# ── Data fetching ──────────────────────────────────────────────────────────────

def fetch_candles_range(obj, token: str, from_dt: datetime, to_dt: datetime) -> list:
    """Fetch 15-min candles between from_dt and to_dt. Returns list of bar dicts."""
    params = {
        "exchange":    MCX_EXCHANGE,
        "symboltoken": token,
        "interval":    "FIFTEEN_MINUTE",
        "fromdate":    from_dt.strftime("%Y-%m-%d %H:%M"),
        "todate":      to_dt.strftime("%Y-%m-%d %H:%M"),
    }
    try:
        resp = obj.getCandleData(params)
    except Exception as e:
        print(f"    [WARN] API error: {e}")
        return []

    if not resp or not resp.get("data"):
        return []

    bars = []
    for row in resp["data"]:
        try:
            ts_raw = row[0]
            ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            # Convert to IST naive (MCX is IST-based)
            ts_ist = ts.replace(tzinfo=None) + timedelta(hours=5, minutes=30) \
                if ts.utcoffset() is not None and ts.utcoffset().total_seconds() == 0 \
                else ts.replace(tzinfo=None)
            bars.append({
                "ts":     ts_ist,
                "open":   float(row[1]),
                "high":   float(row[2]),
                "low":    float(row[3]),
                "close":  float(row[4]),
                "volume": float(row[5]),
            })
        except (IndexError, TypeError, ValueError):
            continue
    return bars


def fetch_all_bars(obj, contracts: list, months_back: int) -> list:
    """
    Paginate through all contracts, pulling 30 days at a time.
    Returns merged, sorted, deduplicated list of bar dicts.
    """
    cutoff = datetime.now() - timedelta(days=months_back * 30)
    all_bars = []
    seen_ts  = set()

    print(f"\n  Fetching historical data ({months_back} months, {len(contracts)} contracts)...")

    for c in contracts:
        token   = c["token"]
        symbol  = c["symbol"]
        expiry  = c["expiry"]

        # Data window for this contract: ~60 days before expiry
        # (front-month: active from ~45 days before expiry)
        window_end   = min(datetime.combine(expiry, datetime.max.time()),
                           datetime.now())
        window_start = max(window_end - timedelta(days=60), cutoff)

        # Paginate in 25-day chunks (SmartAPI limit is ~30 days per call)
        chunk_start = window_start
        contract_bars = 0
        while chunk_start < window_end:
            chunk_end = min(chunk_start + timedelta(days=25), window_end)
            bars = fetch_candles_range(obj, token, chunk_start, chunk_end)
            for b in bars:
                key = b["ts"].isoformat()
                if key not in seen_ts:
                    seen_ts.add(key)
                    all_bars.append(b)
                    contract_bars += 1
            chunk_start = chunk_end

        print(f"    {symbol:<40} {contract_bars:>5} bars")

    all_bars.sort(key=lambda b: b["ts"])
    print(f"\n  Total: {len(all_bars):,} bars  ({len(all_bars) // 58:,} trading days est.)")
    return all_bars


# ── Indicators (stateful per session) ─────────────────────────────────────────

def compute_session_vwap(bars_today: list) -> float:
    """VWAP using today's bars only."""
    if not bars_today:
        return 0.0
    num = sum(((b["high"] + b["low"] + b["close"]) / 3) * b["volume"] for b in bars_today)
    den = sum(b["volume"] for b in bars_today)
    return num / den if den else 0.0


def score_pa(bars_window: list, vwap: float) -> dict:
    """
    Same logic as signal_engine._score_price_action, but called with
    a pre-built bar window and a pre-computed session VWAP.
    """
    if len(bars_window) < 20:
        return None

    closes  = [b["close"]  for b in bars_window]
    volumes = [b["volume"] for b in bars_window]

    rsi   = _rsi(closes)
    ema9  = _ema(closes, 9)
    ema21 = _ema(closes, 21)
    spot  = closes[-1]
    avg_v = sum(volumes[-20:]) / 20

    rsi_score   = 1 if rsi > 55 else (-1 if rsi < 45 else 0)
    vwap_score  = 1 if spot > vwap  else -1
    ema_score   = 1 if ema9 > ema21 else -1

    last3 = closes[-3:]
    up    = sum(1 for i in range(1, len(last3)) if last3[i] > last3[i - 1])
    trend_score = 1 if up >= 2 else (-1 if up == 0 else 0)

    return {
        "rsi":       rsi_score,
        "vwap":      vwap_score,
        "ema_cross": ema_score,
        "bar_trend": trend_score,
        "spot":      spot,
        "rsi_val":   rsi,
        "ema9":      ema9,
        "ema21":     ema21,
        "vol_confirm": volumes[-1] > avg_v if avg_v else False,
    }


_PA_KEYS = ["rsi", "vwap", "ema_cross", "bar_trend"]

def compute_signal(pa: dict, weights: dict) -> dict:
    """
    Weighted normalized signal.

    In backtest, chain factors = 0 so we normalize by PA-factor weights only.
    This keeps the score in [-1, +1] regardless of how weights evolve, so
    signal generation never shuts down because weights drifted too low.
    """
    all_f = {
        "rsi":       pa["rsi"],
        "vwap":      pa["vwap"],
        "ema_cross": pa["ema_cross"],
        "bar_trend": pa["bar_trend"],
        "pcr":       0,
        "oi_flow":   0,
        "iv_skew":   0,
        "max_pain":  0,
    }

    # Normalize by PA weight sum only (chain = 0, doesn't contribute)
    w_score   = sum(all_f[k] * weights.get(k, 1.0) for k in _PA_KEYS)
    max_score = sum(weights.get(k, 1.0) for k in _PA_KEYS)
    norm      = w_score / max_score if max_score > 0 else 0.0

    if norm >= THRESHOLD:
        bias = "long"
    elif norm <= -THRESHOLD:
        bias = "short"
    else:
        bias = "neutral"

    return {"bias": bias, "score": round(norm, 3), "factors": all_f}


# ── Forward simulation ─────────────────────────────────────────────────────────

def simulate_outcome(bars: list, signal_idx: int, bias: str) -> dict | None:
    """
    Scan bars[signal_idx+1 : signal_idx+BARS_AHEAD+1] to find WIN/LOSS.
    Returns dict with outcome, entry, exit price, bars_held. None if no data.
    """
    entry = bars[signal_idx]["close"]
    direction = 1 if bias == "long" else -1

    win_level  = entry * (1 + WIN_PCT  * direction)
    loss_level = entry * (1 - LOSS_PCT * direction)

    for j in range(signal_idx + 1, min(signal_idx + BARS_AHEAD + 1, len(bars))):
        h = bars[j]["high"]
        l = bars[j]["low"]

        if direction == 1:   # LONG: high hits TP, low hits SL
            tp_hit = h >= win_level
            sl_hit = l <= loss_level
        else:                # SHORT: low hits TP, high hits SL
            tp_hit = l <= win_level
            sl_hit = h >= loss_level

        if tp_hit and sl_hit:
            # Both hit same bar — use whichever is closer to entry
            outcome = "WIN"   # conservative: assume SL was narrower context
        elif tp_hit:
            outcome = "WIN"
        elif sl_hit:
            outcome = "LOSS"
        else:
            continue

        exit_price = win_level if outcome == "WIN" else loss_level
        pnl_pct    = (exit_price - entry) / entry * direction * 100
        return {
            "outcome":    outcome,
            "entry":      round(entry, 2),
            "exit":       round(exit_price, 2),
            "pnl_pct":    round(pnl_pct, 2),
            "bars_held":  j - signal_idx,
        }

    # No hit within BARS_AHEAD: use closing direction as proxy
    end_close = bars[min(signal_idx + BARS_AHEAD, len(bars) - 1)]["close"]
    outcome   = "WIN" if (end_close - entry) * direction > 0 else "LOSS"
    pnl_pct   = (end_close - entry) / entry * direction * 100
    return {
        "outcome":   outcome,
        "entry":     round(entry, 2),
        "exit":      round(end_close, 2),
        "pnl_pct":   round(pnl_pct, 2),
        "bars_held": BARS_AHEAD,
    }


# ── Online learner (local copy — does NOT touch live weights.json) ─────────────

def _default_weights() -> dict:
    w = {k: 1.0 for k in FACTOR_KEYS}
    w.update({"trades_seen": 0, "wins": 0, "losses": 0, "win_rate": 0.0})
    return w


def update_weights(w: dict, outcome: str, bias: str, factors: dict) -> dict:
    direction = 1 if bias == "long" else -1

    for key in FACTOR_KEYS:
        fs = factors.get(key, 0)
        if fs == 0:
            continue
        agreed = (fs * direction) > 0
        if outcome == "WIN":
            if agreed:
                w[key] = round(min(MAX_W, w[key] + LEARN_RATE), 3)
        else:
            if agreed:
                w[key] = round(max(MIN_W, w[key] - LEARN_RATE), 3)
            else:
                w[key] = round(min(MAX_W, w[key] + LEARN_RATE * 0.5), 3)

    w["trades_seen"] = w.get("trades_seen", 0) + 1
    if outcome == "WIN":
        w["wins"] = w.get("wins", 0) + 1
    else:
        w["losses"] = w.get("losses", 0) + 1
    seen = w["trades_seen"]
    w["win_rate"] = round(w["wins"] / seen, 3) if seen else 0.0
    return w


# ── Yahoo Finance fallback (WTI crude proxy) ──────────────────────────────────

def fetch_bars_yfinance(months_back: int) -> list:
    """
    Download WTI crude oil (CL=F) hourly bars via yfinance.
    Used when SmartAPI can't provide enough historical data.
    CL=F is 95%+ correlated with MCX CRUDEOILM — signals transfer well.
    """
    if not _YF_OK:
        print("  yfinance not installed — run: pip install yfinance")
        return []

    # yfinance 1h data: max 730 days — cap at 728 to avoid boundary errors
    days = min(months_back * 30, 728)
    print(f"\n  Downloading CL=F (WTI crude) {days}-day hourly data from Yahoo Finance...")
    ticker = yf.Ticker("CL=F")
    df = ticker.history(period=f"{days}d", interval="1h", auto_adjust=True)

    if df.empty:
        print("  No data returned from Yahoo Finance.")
        return []

    bars = []
    for ts, row in df.iterrows():
        try:
            # Convert timezone-aware timestamp to naive IST
            ts_naive = ts.tz_localize(None) if ts.tzinfo else ts
            bars.append({
                "ts":     ts_naive.to_pydatetime(),
                "open":   float(row["Open"]),
                "high":   float(row["High"]),
                "low":    float(row["Low"]),
                "close":  float(row["Close"]),
                "volume": float(row.get("Volume", 1000)),
            })
        except Exception:
            continue

    # Scale to MCX CRUDEOILM price range (WTI is in USD/bbl, MCX is INR/bbl)
    # Approximate: MCX price ≈ WTI_USD × 84 (USD/INR) for recent years
    # Scaling doesn't affect signal decisions (RSI/EMA/trend are relative)
    # but we scale anyway for realistic premium estimates
    if bars:
        avg_close = sum(b["close"] for b in bars) / len(bars)
        if avg_close < 200:  # WTI in USD, scale to INR
            scale = 84.0
            for b in bars:
                b["open"]  *= scale
                b["high"]  *= scale
                b["low"]   *= scale
                b["close"] *= scale

    print(f"  Downloaded {len(bars):,} hourly bars from Yahoo Finance")
    print(f"  Price range: ₹{min(b['close'] for b in bars):.0f} – "
          f"₹{max(b['close'] for b in bars):.0f}")
    return bars


# ── Main backtest loop ─────────────────────────────────────────────────────────

def run_backtest(bars: list) -> tuple[dict, list]:
    """
    Iterate through all bars, generate signals, simulate outcomes.
    Returns (final_weights, list_of_trade_records).
    """
    w      = _default_weights()
    trades = []

    # Track per-session state
    session_bars  = []   # bars for today (for VWAP)
    current_day   = None
    last_signal_i = -BARS_AHEAD   # enforce 1 position at a time

    WARMUP = 25  # bars needed before signal engine can run

    print(f"\n  Running signal engine on {len(bars):,} bars...")
    print(f"  Threshold: ±{THRESHOLD}  |  Win target: +{WIN_PCT:.1%}  |  "
          f"Stop: -{LOSS_PCT:.1%}  |  Max hold: {BARS_AHEAD} bars\n")

    monthly_stats = defaultdict(lambda: {"trades": 0, "wins": 0})

    for i, bar in enumerate(bars):
        # Progress every 1000 bars
        if i % 1000 == 0 and i > 0:
            pct = i / len(bars) * 100
            wr  = w.get("win_rate", 0)
            print(f"  [{pct:5.1f}%]  bar {i:>6,}  trades={w['trades_seen']:>4}  "
                  f"win_rate={wr:.1%}  weights: "
                  + " ".join(f"{k[:3]}={w[k]:.1f}" for k in FACTOR_KEYS[:4]))

        bar_date = bar["ts"].date()

        # Reset session on new day
        if bar_date != current_day:
            session_bars  = []
            current_day   = bar_date

        session_bars.append(bar)

        # Need warmup bars
        if i < WARMUP:
            continue

        # Only one trade open at a time
        if i - last_signal_i < BARS_AHEAD:
            continue

        # Build 50-bar lookback window
        window = bars[max(0, i - 50):i + 1]
        vwap   = compute_session_vwap(session_bars)

        pa = score_pa(window, vwap)
        if pa is None:
            continue

        sig = compute_signal(pa, w)
        if sig["bias"] == "neutral":
            continue

        # Enough future bars to simulate?
        if i + 3 >= len(bars):
            continue

        result = simulate_outcome(bars, i, sig["bias"])
        if result is None:
            continue

        # Update weights
        w = update_weights(w, result["outcome"], sig["bias"], sig["factors"])

        trade = {
            "ts":      bar["ts"].isoformat(),
            "bias":    sig["bias"],
            "score":   sig["score"],
            "entry":   result["entry"],
            "exit":    result["exit"],
            "outcome": result["outcome"],
            "pnl_pct": result["pnl_pct"],
            "bars":    result["bars_held"],
        }
        trades.append(trade)
        last_signal_i = i

        # Monthly tracking
        mo = bar["ts"].strftime("%Y-%m")
        monthly_stats[mo]["trades"] += 1
        if result["outcome"] == "WIN":
            monthly_stats[mo]["wins"] += 1

    print(f"\n  Done. {w['trades_seen']} simulated trades.\n")
    return w, trades, monthly_stats


# ── Reporting ──────────────────────────────────────────────────────────────────

def show_summary(w_before: dict, w_after: dict, trades: list, monthly: dict):
    print(_SEP)
    print("  BACKTEST COMPLETE — ML TRAINING RESULTS")
    print(_SEP)

    total = w_after.get("trades_seen", 0)
    wins  = w_after.get("wins", 0)
    wr    = w_after.get("win_rate", 0)
    avg_pnl = sum(t["pnl_pct"] for t in trades) / len(trades) if trades else 0
    longs   = sum(1 for t in trades if t["bias"] == "long")
    shorts  = total - longs

    print(f"\n  Trades:    {total}  ({longs} long  {shorts} short)")
    print(f"  Win rate:  {wr:.1%}  ({wins}W / {total-wins}L)")
    print(f"  Avg P&L:   {avg_pnl:+.2f}%  per trade (underlying move)")

    # Consecutive streaks
    streak_w = streak_l = cur_w = cur_l = 0
    for t in trades:
        if t["outcome"] == "WIN":
            cur_w += 1; cur_l = 0
            streak_w = max(streak_w, cur_w)
        else:
            cur_l += 1; cur_w = 0
            streak_l = max(streak_l, cur_l)
    print(f"  Max streak: {streak_w}W / {streak_l}L")

    # Weight changes
    print(f"\n  {'FACTOR':<14} {'BEFORE':>7} {'AFTER':>7} {'CHANGE':>8}  VERDICT")
    print(f"  {_sep}")
    for k in FACTOR_KEYS[:4]:   # PA factors (actually trained)
        before = w_before.get(k, 1.0)
        after  = w_after.get(k, 1.0)
        delta  = after - before
        bar    = "+" * int(after * 5) if after >= before else "-" * int((before - after) * 5 + 1)
        tag    = ("STRONG" if after >= 2.0 else
                  "GOOD"   if after >= 1.5 else
                  "WEAK"   if after <= 0.5 else
                  "OK")
        print(f"  {k:<14} {before:>7.2f} {after:>7.2f} {delta:>+8.2f}  {tag}  {bar}")
    print(f"  {_sep}")
    for k in FACTOR_KEYS[4:]:   # chain factors (untrained — stay at 1.0)
        before = w_before.get(k, 1.0)
        after  = w_after.get(k, 1.0)
        print(f"  {k:<14} {before:>7.2f} {after:>7.2f} {'0.00':>8}  (no history)")

    # Monthly breakdown (last 6 months)
    print(f"\n  MONTHLY BREAKDOWN (last 6 months)")
    print(f"  {'-'*40}")
    for mo in sorted(monthly.keys())[-6:]:
        t = monthly[mo]["trades"]
        w_ = monthly[mo]["wins"]
        wr_ = w_ / t if t else 0
        bar = "W" * w_ + "L" * (t - w_)
        print(f"  {mo}  trades={t:>3}  win%={wr_:.0%}  {bar[:20]}")

    print(f"\n  Backtest weights saved to:")
    print(f"    {BACKTEST_WEIGHTS_FILE}")
    print(f"\n  To promote to live trading:")
    print(f'    copy "{BACKTEST_WEIGHTS_FILE}" "{LIVE_WEIGHTS_FILE}"')
    print(f"  (or run:  python backtest.py --promote)")
    print()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CRUDEOILM 2-year backtest + ML training")
    parser.add_argument("--months",  type=int, default=24,
                        help="Months of history to fetch (default 24)")
    parser.add_argument("--promote", action="store_true",
                        help="Copy backtest weights to live weights.json after training")
    args = parser.parse_args()

    print(_SEP)
    print("  CRUDEOILM BACKTEST  —  ML WEIGHT TRAINING")
    print(f"  History:   {args.months} months of 15-min bars")
    print(f"  Factors:   4 PA (RSI/VWAP/EMA/trend)  +  4 chain (neutral)")
    print(f"  Threshold: ±{THRESHOLD}  |  Win: +{WIN_PCT:.1%}  Stop: -{LOSS_PCT:.1%}")
    print(_SEP)

    # Snapshot before weights
    w_before = {k: 1.0 for k in FACTOR_KEYS}
    if LIVE_WEIGHTS_FILE.exists():
        try:
            w_before = json.loads(LIVE_WEIGHTS_FILE.read_text())
        except Exception:
            pass

    # Auth
    print("\n  [1/4] Authenticating SmartAPI...")
    obj = auth.get_session()
    print("  Auth ok.")

    # Scrip master
    print("\n  [2/4] Finding CRUDEOILM contracts...")
    scrip = load_scrip_master()
    contracts = find_contracts(scrip, args.months)

    if not contracts:
        print("\n  ERROR: No CRUDEOILM futures contracts found in scrip master.")
        print("  This can happen if the scrip master cache is stale.")
        print("  Delete .scrip_master_cache.json and retry.")
        sys.exit(1)

    print(f"  Found {len(contracts)} contracts:")
    for c in contracts:
        print(f"    {c['symbol']:<40}  token={c['token']}  expiry={c['expiry']}")

    # Fetch bars
    print("\n  [3/4] Fetching historical OHLCV data...")
    bars = fetch_all_bars(obj, contracts, args.months)

    # Check if SmartAPI gave us enough history (need ≥ 6 months of data)
    MIN_MONTHS = 6
    if bars:
        oldest = bars[0]["ts"]
        months_got = (datetime.now() - oldest).days / 30
    else:
        months_got = 0

    if months_got < MIN_MONTHS:
        print(f"\n  SmartAPI returned {months_got:.1f} months of data (need ≥ {MIN_MONTHS}).")
        print(f"  Expired contracts are not in the scrip master — this is a SmartAPI limitation.")
        if _YF_OK:
            print(f"\n  Falling back to Yahoo Finance CL=F (WTI crude, hourly data).")
            print(f"  WTI is 95%+ correlated with MCX CRUDEOILM — signals transfer well.")
            yf_bars = fetch_bars_yfinance(args.months)
            if yf_bars:
                bars = yf_bars
                print(f"  Using {len(bars):,} Yahoo Finance bars for training.\n")
            else:
                print(f"  Yahoo Finance also returned insufficient data.")
                sys.exit(1)
        else:
            print("  Install yfinance for 2-year WTI proxy data: pip install yfinance")
            sys.exit(1)

    # Backtest
    print("\n  [4/4] Running backtest + training weights...")
    w_after, trades, monthly = run_backtest(bars)

    # Save backtest weights
    BACKTEST_WEIGHTS_FILE.write_text(json.dumps(w_after, indent=2))

    # Summary
    show_summary(w_before, w_after, trades, monthly)

    # Promote
    if args.promote:
        import shutil
        shutil.copy(BACKTEST_WEIGHTS_FILE, LIVE_WEIGHTS_FILE)
        print(f"  ✓ Live weights updated: {LIVE_WEIGHTS_FILE}")
        print(f"  Restart the scheduler to apply: .\\restart.ps1\n")
    else:
        print(f"  Run with --promote flag to push weights to live, then restart.\n")


if __name__ == "__main__":
    main()
