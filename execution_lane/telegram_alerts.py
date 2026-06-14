# -*- coding: utf-8 -*-
"""
Telegram alert sender.

Setup (one time):
  1. Message @BotFather on Telegram -> /newbot -> copy the token
  2. Start a chat with your new bot, send any message
  3. Visit: https://api.telegram.org/bot<TOKEN>/getUpdates
     Find "chat":{"id": <NUMBER>} — that's your CHAT_ID
  4. Add to .env:
       TELEGRAM_BOT_TOKEN=123456789:ABCdef...
       TELEGRAM_CHAT_ID=987654321
"""
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def _send(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception:
        pass   # Telegram failure must never crash the trading loop


def trade_opened(selection: dict, risk: dict, signal: dict, gtt_rule_id: str = ""):
    bias = selection["bias"].upper()
    opt  = selection["option_type"]
    stk  = selection["strike"]
    ltp  = risk["ltp"]
    sl   = risk["sl_premium"]
    tp   = risk["tp_premium"]
    sc   = signal.get("score", 0)
    und  = signal.get("underlying", 0)
    mode = "PAPER" if selection.get("mode", "PAPER") == "PAPER" else "LIVE"
    gtt_line = f"\nGTT: `{gtt_rule_id}` (exchange-side exit armed 🔐)" if gtt_rule_id else ""
    _send(
        f"*TRADE OPEN* {'📈' if bias == 'LONG' else '📉'}\n"
        f"`{bias}  {opt} {stk:.0f}  @  Rs{ltp:.1f}`\n"
        f"SL Rs{sl:.1f}  |  TP Rs{tp:.1f}\n"
        f"Signal score: {sc:+.2f}  |  Spot: Rs{und:.0f}\n"
        f"Mode: {mode}{gtt_line}"
    )


def trade_closed(trade: dict):
    outcome = trade.get("outcome", "?")
    icon    = "✅" if outcome == "WIN" else "❌"
    pnl     = trade.get("pnl", 0)
    _send(
        f"{icon} *{outcome}*  {trade.get('option','')}\n"
        f"Entry Rs{trade['entry_ltp']:.1f}  ->  Exit Rs{trade.get('exit_ltp',0):.1f}\n"
        f"P&L: `Rs{pnl:+.0f}`"
    )


def claude_vetoed(signal: dict, reason: str):
    _send(
        f"*TRADE VETOED by Claude* ⛔\n"
        f"Signal was {signal.get('bias','?').upper()} "
        f"(score {signal.get('score',0):+.2f})\n"
        f"Reason: _{reason}_"
    )


def signal_fired(signal: dict):
    bias = signal.get("bias", "neutral").upper()
    sc   = signal.get("score", 0)
    und  = signal.get("underlying", 0)
    rsi  = signal.get("rsi", 0)
    conv = signal.get("conviction", 0)
    if bias == "NEUTRAL":
        return
    icon = "📈" if bias == "LONG" else "📉"
    _send(
        f"{icon} *SIGNAL {bias}*  score {sc:+.3f}  conviction {conv}/10\n"
        f"Spot Rs{und:.0f}  |  RSI {rsi:.1f}\n"
        f"Sending to Claude for review..."
    )


def signal_fired_skipped(signal: dict, reason: str):
    bias = signal.get("bias", "neutral").upper()
    sc   = signal.get("score", 0)
    _send(
        f"*SIGNAL {bias} — SKIPPED* score {sc:+.3f}\n"
        f"_{reason}_"
    )


def scheduler_error(err: str):
    _send(f"*SCHEDULER ERROR* 🚨\n`{err[:300]}`")


def hourly_status(stats: dict, weights: dict, in_market: bool):
    """
    Hourly heartbeat sent every 60 minutes.
    stats keys: cycles, longs, shorts, neutrals, trades_opened,
                trades_closed, errors, risk_blocks, claude_skips,
                open_positions, spot, hour_start, hour_end
    """
    hour_start = stats.get("hour_start", "")
    hour_end   = stats.get("hour_end", "")
    cycles     = stats.get("cycles", 0)
    longs      = stats.get("longs", 0)
    shorts     = stats.get("shorts", 0)
    neutrals   = stats.get("neutrals", 0)
    t_opened   = stats.get("trades_opened", 0)
    t_closed   = stats.get("trades_closed", [])
    errors     = stats.get("errors", [])
    risk_blk   = stats.get("risk_blocks", 0)
    c_skips    = stats.get("claude_skips", 0)
    n_open     = stats.get("open_positions", 0)
    spot       = stats.get("spot", 0)

    # Status icon
    if not in_market:
        status = "SLEEPING (market closed)"
        icon   = "💤"
    elif errors:
        status = f"RUNNING with {len(errors)} error(s)"
        icon   = "⚠️"
    else:
        status = "RUNNING"
        icon   = "✅"

    # Signals line
    sig_parts = []
    if longs:    sig_parts.append(f"LONG×{longs}")
    if shorts:   sig_parts.append(f"SHORT×{shorts}")
    if neutrals: sig_parts.append(f"NEUTRAL×{neutrals}")
    sig_str = "  ".join(sig_parts) if sig_parts else "none"

    # Trades closed this hour
    closed_str = ""
    for t in t_closed:
        icon_t = "✅" if t.get("outcome") == "WIN" else "❌"
        closed_str += f"\n  {icon_t} {t.get('option','')}  Rs{t.get('pnl',0):+.0f}"

    # Errors (truncated)
    err_str = ""
    if errors:
        for e in errors[-3:]:
            err_str += f"\n  🚨 {str(e)[:80]}"

    # Skips
    skip_str = ""
    if risk_blk or c_skips:
        skip_str = f"\nBlocked: risk×{risk_blk}  Claude×{c_skips}"

    # Weights (top 4 only)
    w_keys = ["bar_trend", "ema_cross", "vwap", "rsi"]
    w_str  = "  ".join(f"{k[:3]}={weights.get(k,1.0):.2f}" for k in w_keys)

    lines = [
        f"{icon} *HOURLY STATUS*  {hour_start} – {hour_end}",
        f"Bot: {status}",
        f"Cycles: {cycles}  |  Signals: {sig_str}",
        f"Trades opened: {t_opened}  |  Open now: {n_open}",
    ]
    if closed_str:
        lines.append(f"Closed this hour:{closed_str}")
    if skip_str:
        lines.append(skip_str)
    if spot:
        lines.append(f"Spot: Rs{spot:.0f}")
    lines.append(f"Weights: `{w_str}`")
    if err_str:
        lines.append(f"Errors:{err_str}")

    _send("\n".join(lines))


def daily_summary(weights: dict, trades_today: list):
    wins   = sum(1 for t in trades_today if t.get("outcome") == "WIN")
    losses = sum(1 for t in trades_today if t.get("outcome") == "LOSS")
    pnl    = sum(t.get("pnl", 0) for t in trades_today)
    top3   = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:3]
    top_str = "  ".join(f"{k}={v:.2f}" for k, v in top3 if k not in ("trades_seen","wins","losses","win_rate"))
    _send(
        f"*DAILY SUMMARY* 📊\n"
        f"Trades: {wins+losses}  |  W/L: {wins}/{losses}  |  P&L: Rs{pnl:+.0f}\n"
        f"Win rate: {weights.get('win_rate',0):.1%}\n"
        f"Top factors: {top_str}"
    )
