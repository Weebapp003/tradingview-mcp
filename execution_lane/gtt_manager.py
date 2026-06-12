# -*- coding: utf-8 -*-
"""
GTT (Good Till Triggered) exit orders — live mode only.

After a live entry is filled, places a TWO-LEG GTT on the exchange:
  Leg 1: SELL at sl_premium (stop-loss)  — triggers when LTP falls to SL
  Leg 2: SELL at tp_premium (take-profit) — triggers when LTP rises to TP

When one leg fires, the other is automatically cancelled (OCO).
Exchange handles the exit with zero latency — no Python loop needed.

GTT rule ID is saved to the trade log entry so it can be cancelled
or inspected later.
"""
import json
from datetime import date

from config import MCX_EXCHANGE, LOG_DIR

_TRADE_LOG = LOG_DIR / f"trades_{date.today():%Y%m%d}.json"


def place_exit_gtt(obj, trade: dict, sl_premium: float, tp_premium: float) -> str:
    """
    Place a TWO-LEG GTT order to exit a live position.

    Args:
        obj:         SmartConnect session
        trade:       trade log entry dict
        sl_premium:  stop-loss premium level (SELL triggered when LTP <= this)
        tp_premium:  take-profit premium level (SELL triggered when LTP >= this)

    Returns:
        GTT rule ID string, or "" on failure
    """
    qty = trade["qty_lots"] * trade["lot_size"]

    gtt_params = {
        "tradingsymbol": trade["instrument"],
        "symboltoken":   trade["token"],
        "exchange":      MCX_EXCHANGE,
        "producttype":   "CARRYFORWARD",
        "transactiontype": "SELL",
        "qty":           qty,
        "disclosedqty":  qty,
        "timeperiod":    1,          # expire EOD — reset each morning
        "price":         [
            round(sl_premium * 0.95, 1),   # SL limit: 5% below trigger for fill assurance
            round(tp_premium, 1),           # TP limit: at target price
        ],
        "triggerprice":  [sl_premium, tp_premium],
        "type":          "TWO-LEG",
    }

    try:
        resp    = obj.gttCreateRule(gtt_params)
        rule_id = str((resp or {}).get("data", {}).get("id", ""))
        print(f"  [GTT] Exit GTT placed — rule_id={rule_id}  "
              f"SL Rs{sl_premium}  TP Rs{tp_premium}")
        _save_gtt_id(trade.get("order_id", ""), rule_id)
        return rule_id
    except Exception as e:
        print(f"  [GTT] Failed: {e} — fall back to 60-sec monitor")
        return ""


def cancel_gtt(obj, rule_id: str, symbol: str, token: str) -> bool:
    """Cancel a GTT rule (e.g. if we manually exit first)."""
    if not rule_id:
        return False
    try:
        obj.gttDeleteRule({
            "id":            rule_id,
            "tradingsymbol": symbol,
            "symboltoken":   token,
            "exchange":      MCX_EXCHANGE,
        })
        print(f"  [GTT] Rule {rule_id} cancelled")
        return True
    except Exception as e:
        print(f"  [GTT] Cancel failed: {e}")
        return False


def _save_gtt_id(order_id: str, rule_id: str):
    """Patch the trade log entry with the GTT rule ID."""
    if not _TRADE_LOG.exists() or not order_id:
        return
    try:
        trades = json.loads(_TRADE_LOG.read_text())
        for t in trades:
            if t.get("order_id") == order_id:
                t["gtt_rule_id"] = rule_id
                break
        _TRADE_LOG.write_text(json.dumps(trades, indent=2, default=str))
    except Exception:
        pass
