# -*- coding: utf-8 -*-
"""
Position monitor: checks every OPEN paper trade each cycle.
Closes the position when current LTP crosses SL or TP.
Records the outcome for the online learner.
"""
import json
from datetime import datetime, date

from config import LOG_DIR
from option_chain import _fetch_quotes

_TRADE_LOG   = LOG_DIR / f"trades_{date.today():%Y%m%d}.json"
_OUTCOME_LOG = LOG_DIR / f"outcomes_{date.today():%Y%m%d}.jsonl"


def _load_trades() -> list:
    if not _TRADE_LOG.exists():
        return []
    try:
        return json.loads(_TRADE_LOG.read_text())
    except Exception:
        return []


def _save_trades(trades: list):
    _TRADE_LOG.write_text(json.dumps(trades, indent=2, default=str))


def _log_outcome(trade: dict):
    with open(_OUTCOME_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(trade, default=str) + "\n")


def check_and_close(obj) -> list:
    """
    Fetch current LTP for every OPEN position.
    Close (and record) any that have hit SL or TP.
    Returns list of newly closed trade dicts.
    """
    trades = _load_trades()
    open_trades = [t for t in trades if t.get("status") == "OPEN"]
    if not open_trades:
        return []

    tokens = [t["token"] for t in open_trades]
    quotes = _fetch_quotes(obj, tokens)

    newly_closed = []
    changed      = False

    for trade in trades:
        if trade.get("status") != "OPEN":
            continue

        tok         = trade["token"]
        q           = quotes.get(tok, {})
        current_ltp = float(q.get("ltp") or q.get("close") or 0)

        if current_ltp <= 0:
            continue

        sl    = trade["sl_premium"]
        tp    = trade["tp_premium"]
        entry = trade["entry_ltp"]
        lots  = trade["qty_lots"]
        lot   = trade["lot_size"]

        if current_ltp <= sl:
            outcome = "LOSS"
        elif current_ltp >= tp:
            outcome = "WIN"
        else:
            continue

        pnl = round((current_ltp - entry) * lots * lot, 2)

        trade["status"]   = "CLOSED"
        trade["exit_ltp"] = current_ltp
        trade["exit_ts"]  = datetime.now().isoformat()
        trade["outcome"]  = outcome
        trade["pnl"]      = pnl

        _log_outcome(trade)
        newly_closed.append(dict(trade))
        changed = True

    if changed:
        _save_trades(trades)

    return newly_closed


def open_count() -> int:
    """Return number of OPEN positions today."""
    return sum(1 for t in _load_trades() if t.get("status") == "OPEN")
