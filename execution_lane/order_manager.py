"""
Order execution: paper simulation or live SmartAPI placement.
All trades are appended to a dated JSON log regardless of mode.
"""
import json
from datetime import datetime

from config import MCX_EXCHANGE, PAPER, LOG_DIR

_TRADE_LOG = LOG_DIR / f"trades_{datetime.now():%Y%m%d}.json"


def _append_trade(entry: dict):
    trades = []
    if _TRADE_LOG.exists():
        try:
            trades = json.loads(_TRADE_LOG.read_text())
        except Exception:
            pass
    trades.append(entry)
    _TRADE_LOG.write_text(json.dumps(trades, indent=2, default=str))


def execute(obj, selection: dict, risk: dict, paper: bool = PAPER) -> dict:
    qty         = risk["qty"]
    lot         = risk["lot"]
    ltp         = risk["ltp"]
    token       = selection["token"]
    tradingsym  = selection.get("tradingsymbol", "")
    opt_type    = selection["option_type"]
    strike      = selection["strike"]
    bias        = selection["bias"]

    order_params = {
        "variety":         "NORMAL",
        "tradingsymbol":   tradingsym,
        "symboltoken":     token,
        "transactiontype": "BUY",
        "exchange":        MCX_EXCHANGE,
        "ordertype":       "LIMIT",
        "producttype":     "CARRYFORWARD",
        "duration":        "DAY",
        "price":           str(round(ltp * 1.01, 1)),  # 1% buffer above LTP for limit fill
        "quantity":        str(qty * lot),              # SmartAPI takes total units
        "squareoff":       "0",
        "stoploss":        "0",
        "triggerprice":    "0",
    }

    trade_log_entry = {
        "ts":           datetime.now().isoformat(),
        "mode":         "PAPER" if paper else "LIVE",
        "bias":         bias,
        "action":       "BUY",
        "instrument":   tradingsym,
        "option":       f"{opt_type} {strike:.0f}",
        "token":        token,
        "qty_lots":     qty,
        "lot_size":     lot,
        "entry_ltp":    ltp,
        "sl_premium":   risk["sl_premium"],
        "tp_premium":   risk["tp_premium"],
        "max_risk_rs":  risk["max_loss_rs"],
        "order_params": order_params,
        "pnl":          0.0,
        "status":       "OPEN",
        "order_id":     None,
    }

    # ── PAPER ─────────────────────────────────────────────────────────────────
    if paper:
        trade_log_entry["order_id"] = f"PAPER_{datetime.now():%H%M%S}"
        _append_trade(trade_log_entry)
        return {
            "success":  True,
            "mode":     "PAPER",
            "order_id": trade_log_entry["order_id"],
            "detail":   (
                f"[PAPER] BUY {qty} lot(s) {opt_type} {strike:.0f} @ ₹{ltp:.1f} | "
                f"SL ₹{risk['sl_premium']} | TP ₹{risk['tp_premium']} | "
                f"Max risk ₹{risk['max_loss_rs']:,.0f}"
            ),
        }

    # ── LIVE ──────────────────────────────────────────────────────────────────
    print(f"\n  {'!'*60}")
    print(f"  LIVE ORDER: BUY {qty} lot(s) × {lot} = {qty*lot} units")
    print(f"  {opt_type} {strike:.0f}  {tradingsym}")
    print(f"  Limit price ₹{float(order_params['price']):.1f}  |  "
          f"SL ₹{risk['sl_premium']}  |  TP ₹{risk['tp_premium']}")
    print(f"  Max risk ₹{risk['max_loss_rs']:,.0f}")
    print(f"  {'!'*60}")
    confirm = input("  Type YES to place order: ").strip()
    if confirm != "YES":
        return {"success": False, "mode": "LIVE", "detail": "Order cancelled by user"}

    try:
        resp     = obj.placeOrder(order_params)
        order_id = (resp or {}).get("data", {}).get("orderid")
        trade_log_entry["order_id"] = order_id
        trade_log_entry["status"]   = "PLACED"
        _append_trade(trade_log_entry)
        return {
            "success":  True,
            "mode":     "LIVE",
            "order_id": order_id,
            "detail":   f"Order placed — ID: {order_id}",
        }
    except Exception as e:
        return {"success": False, "mode": "LIVE", "detail": f"Order failed: {e}"}
