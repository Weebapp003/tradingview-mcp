# -*- coding: utf-8 -*-
"""
Phase 2 scheduler — runs the full auto-signal pipeline every 15 minutes
during MCX crude market hours (09:00–23:30 IST, Mon–Fri).

Usage:
  python scheduler.py           # paper mode (uses PAPER env var)
  python scheduler.py --live    # live mode (requires PAPER=false in .env)

Ctrl+C to stop.
"""
import sys
import logging
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
logging.disable(logging.INFO)

import argparse
import time
from datetime import datetime, time as dtime
from pathlib import Path

import auth
import option_chain as oc
import chain_analyzer as ca
import strike_selector as ss
import risk_gate as rg
import order_manager as om
import signal_engine as se
import position_monitor as pm
import online_learner as ol
import claude_reviewer as cr
import telegram_alerts as tg
from config import FULL_NAME, MINI_NAME, PAPER, ATM_WINGS, LOG_DIR

MARKET_OPEN  = dtime(9, 0)
MARKET_CLOSE = dtime(23, 30)
INTERVAL_MIN = 15


# ── Market hours check ────────────────────────────────────────────────────────

def in_market_hours() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:          # Saturday=5, Sunday=6
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


def minutes_to_open() -> int:
    """Minutes until next market open (for sleep message)."""
    now  = datetime.now()
    open_today = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now.time() < MARKET_OPEN:
        return int((open_today - now).total_seconds() / 60)
    return int((open_today.replace(day=now.day + 1) - now).total_seconds() / 60)



# ── Display helpers ───────────────────────────────────────────────────────────

_BAR = "═" * 66
_bar = "─" * 66


def _print_signal(sig: dict):
    icon = lambda s: "+" if s > 0 else ("-" if s < 0 else "·")
    print(f"\n  {'SIGNAL':─<62}")
    print(f"  Bias: {sig['bias'].upper():<10}  Score: {sig['score']:+.3f}  "
          f"Conviction: {sig['conviction']}/10  "
          f"Vol confirm: {'yes' if sig['vol_confirm'] else 'no'}")
    print(f"  RSI {sig['rsi']:.1f}  |  VWAP {sig['vwap']:.0f}  |  "
          f"Underlying {sig['underlying']:.0f}")
    print(f"  {'Price action':─<30}  {'Chain':─<28}")
    for (k1, v1), (k2, v2) in zip(
            sig["pa_factors"].items(), sig["ch_factors"].items()):
        print(f"  [{icon(v1['score'])}] {v1['label']:<30}  [{icon(v2['score'])}] {v2['label']}")
    if sig["bias"] != "neutral":
        tgt = " / ".join(f"{t:.0f}" for t in sig["auto_targets"])
        print(f"  Stop: {sig['auto_stop']:.0f}  |  Targets: {tgt}")


def _print_result(result: dict, risk: dict, selection: dict):
    icon = "✓" if result["success"] else "✗"
    print(f"\n  {icon} {result['detail']}")
    if result.get("order_id"):
        print(f"  Order ID: {result['order_id']}")
    print(f"  Risk: {risk['reason']}")
    if selection.get("conflicts"):
        for c in selection["conflicts"]:
            print(f"  ⚠ {c}")


# ── Single pipeline cycle ─────────────────────────────────────────────────────

def run_cycle(paper: bool):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n{_BAR}")
    print(f"  CYCLE  {ts}  |  {'PAPER' if paper else 'LIVE ⚠'}")
    print(_BAR)

    # Auth — always fresh
    obj = auth.get_session()
    print(f"  [1] auth ok")

    # [0] Position monitor + online learning
    closed = pm.check_and_close(obj)
    for trade in closed:
        updated_w = ol.update(trade)
        icon      = "WIN +" if trade["outcome"] == "WIN" else "LOSS -"
        print(f"  [LEARN] {icon}  {trade['option']}  "
              f"pnl=Rs{trade['pnl']:+.0f}  "
              f"win_rate={updated_w.get('win_rate', 0):.1%}  "
              f"trades={updated_w.get('trades_seen', 0)}")
        tg.trade_closed(trade)

    # Underlying price
    underlying = oc.get_underlying_price(obj, MINI_NAME)
    print(f"  [2] underlying ₹{underlying:.1f}")

    # Full chain + analysis (OI source)
    full_chain = oc.build_live_chain(obj, FULL_NAME, underlying)
    analysis   = ca.analyze(full_chain, underlying, wings=ATM_WINGS)
    print(f"  [3] chain built  expiry={full_chain['expiry']}  strikes={len(full_chain['strikes'])}")

    # Auto signal
    _, fut_token = oc.get_futures_token(MINI_NAME)
    signal = se.generate(obj, fut_token, analysis)
    print(f"  [4] signal generated")
    _print_signal(signal)

    # Neutral → no trade
    if signal["bias"] == "neutral":
        print(f"\n  NEUTRAL ({signal['score']:+.2f}) — no trade this cycle")
        return

    # Non-neutral signal — alert immediately so user knows bot is active
    tg.signal_fired(signal)

    # Already have an open position → skip
    n_open = pm.open_count()
    if n_open > 0:
        print(f"\n  {n_open} position(s) OPEN — skipping entry this cycle")
        tg.signal_fired_skipped(signal, f"{n_open} position already open")
        return

    # Mini chain + strike selection
    mini_chain = oc.build_live_chain(obj, MINI_NAME, underlying)
    selection  = ss.select(analysis, mini_chain, signal["bias"], signal["conviction"])
    print(f"\n  [5] strike selected: {selection.get('tradingsymbol', '?')}  "
          f"LTP Rs{selection.get('ltp', 0):.1f}")

    # Risk gate
    risk = rg.check(selection, underlying, signal["auto_stop"])
    if not risk["approved"]:
        print(f"  [6] BLOCKED: {risk['reason']}")
        tg.signal_fired_skipped(signal, f"Risk gate: {risk['reason'][:60]}")
        return

    # Claude review — second opinion before pulling the trigger
    print(f"  [6] Asking Claude to review...", end="  ", flush=True)
    decision, reason = cr.review(signal, analysis)
    print(f"{decision} — {reason}")
    if decision == "SKIP":
        tg.claude_vetoed(signal, reason)
        return

    # Execute
    print(f"  [7] Executing...")
    result = om.execute(obj, selection, risk, paper=paper, signal=signal)
    _print_result(result, risk, selection)
    if result["success"]:
        tg.trade_opened(selection, risk, signal, gtt_rule_id=result.get("gtt_rule_id", ""))


# ── Position monitor during sleep ─────────────────────────────────────────────

def _sleep_and_monitor(duration_secs: int):
    """
    Sleep for duration_secs, waking every 60 seconds to check open positions.

    Paper mode: detects SL/TP hits via LTP comparison (no GTT exists for paper).
    Live mode:  GTT fires instantly on exchange; we still check so the Python
                log and learner are updated within 60 seconds of the exit.
    """
    if pm.open_count() == 0:
        time.sleep(duration_secs)
        return

    # Auth once for the whole monitoring window
    try:
        mon_obj = auth.get_session()
    except Exception:
        time.sleep(duration_secs)
        return

    elapsed = 0
    while elapsed < duration_secs:
        chunk = min(60, duration_secs - elapsed)
        time.sleep(chunk)
        elapsed += chunk

        if pm.open_count() == 0:
            # All positions closed — rest of sleep without checking
            remaining = duration_secs - elapsed
            if remaining > 0:
                time.sleep(remaining)
            return

        try:
            for trade in pm.check_and_close(mon_obj):
                updated_w = ol.update(trade)
                icon      = "WIN +" if trade["outcome"] == "WIN" else "LOSS -"
                print(f"  [MONITOR {elapsed//60:.0f}m] {icon}  {trade['option']}  "
                      f"Rs{trade['pnl']:+.0f}  "
                      f"win_rate={updated_w.get('win_rate', 0):.1%}")
                tg.trade_closed(trade)
        except Exception as e:
            print(f"  [MONITOR] check error: {e}")


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CRUDEOIL Auto Signal Scheduler")
    parser.add_argument("--live", action="store_true",
                        help="Enable live trading (overrides PAPER=true)")
    args   = parser.parse_args()
    paper  = not args.live and PAPER

    print(_BAR)
    print(f"  CRUDEOIL AUTO SIGNAL SCHEDULER  v3")
    print(f"  Mode:     {'PAPER' if paper else 'LIVE ⚠  real money'}")
    print(f"  Hours:    {MARKET_OPEN}–{MARKET_CLOSE} IST  (Mon–Fri)")
    print(f"  Interval: {INTERVAL_MIN} min  (positions monitored every 60s)")
    print(f"  Signal:   8 factors, score +-1.0, threshold +-0.375")
    print(f"  Exits:    {'60s poll (paper)' if paper else 'Exchange GTT + 60s backup'}")
    print(_BAR)
    print(f"  Press Ctrl+C to stop.\n")

    _STOP_FLAG = LOG_DIR / "STOP"
    _STOP_FLAG.unlink(missing_ok=True)   # clear any leftover flag from prev session

    while True:
        # Graceful stop: restart.ps1 creates logs/STOP instead of killing the process
        if _STOP_FLAG.exists():
            _STOP_FLAG.unlink(missing_ok=True)
            print(f"\n  [STOP] Stop flag detected — shutting down gracefully.\n")
            break

        try:
            if in_market_hours():
                run_cycle(paper)
            else:
                now = datetime.now()
                print(f"  [{now:%H:%M}] outside market hours", end="")
                if now.weekday() < 5 and now.time() < MARKET_OPEN:
                    print(f" — opens in ~{minutes_to_open()} min")
                else:
                    print(f" — resumes next trading day at 09:00 IST")

        except KeyboardInterrupt:
            print(f"\n\n  Scheduler stopped by user.\n")
            break
        except Exception as exc:
            print(f"\n  [ERROR] {exc}")
            tg.scheduler_error(str(exc))

        print(f"  Sleeping {INTERVAL_MIN} min (monitoring open positions)...\n")
        _sleep_and_monitor(INTERVAL_MIN * 60)


if __name__ == "__main__":
    main()
