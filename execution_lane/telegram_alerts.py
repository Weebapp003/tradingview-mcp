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


def trade_opened(selection: dict, risk: dict, signal: dict):
    bias = selection["bias"].upper()
    opt  = selection["option_type"]
    stk  = selection["strike"]
    ltp  = risk["ltp"]
    sl   = risk["sl_premium"]
    tp   = risk["tp_premium"]
    sc   = signal.get("score", 0)
    und  = signal.get("underlying", 0)
    _send(
        f"*TRADE OPEN* {'📈' if bias == 'LONG' else '📉'}\n"
        f"`{bias}  {opt} {stk:.0f}  @  Rs{ltp:.1f}`\n"
        f"SL Rs{sl:.1f}  |  TP Rs{tp:.1f}\n"
        f"Signal score: {sc:+.2f}  |  Spot: Rs{und:.0f}\n"
        f"Mode: PAPER"
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
