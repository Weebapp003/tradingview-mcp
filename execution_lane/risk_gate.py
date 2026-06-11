"""
Risk gate: position sizing, SL/TP, liquidity check, daily-loss limit.

Sizing logic:
  max_risk_rs     = CAPITAL × MAX_RISK_PCT / 100
  sl_premium      = ltp × 50% (default option SL)
  qty (lots)      = floor(max_risk_rs / (sl_premium × lot_size))
  max_loss_rs     = qty × lot_size × sl_premium
"""
import json
from datetime import date

from config import CAPITAL, MAX_RISK_PCT, DAILY_LOSS_LIMIT_PCT, LOG_DIR

_DAILY_PNL_FILE = LOG_DIR / f"pnl_{date.today():%Y%m%d}.json"


def _today_realised_loss() -> float:
    """Returns today's total realised loss (positive = loss)."""
    if not _DAILY_PNL_FILE.exists():
        return 0.0
    try:
        entries = json.loads(_DAILY_PNL_FILE.read_text())
        losses  = sum(e.get("pnl", 0) for e in entries if e.get("pnl", 0) < 0)
        return abs(losses)
    except Exception:
        return 0.0


def check(selection: dict, underlying: float, stop_level: float) -> dict:
    """
    Returns approval dict:
      {approved, qty, ltp, lot, max_loss_rs, sl_premium, tp_premium, reason}
    """
    if not selection.get("action"):
        return {"approved": False, "reason": "No trade — neutral bias or no valid strike found"}

    ltp    = selection["ltp"]
    lot    = selection["lot"]
    volume = selection.get("volume", 0)
    bid    = selection.get("bid", 0)
    ask    = selection.get("ask", 0)

    # ── Liquidity checks ───────────────────────────────────────────────────────
    if ltp <= 0:
        return {"approved": False,
                "reason": f"Zero LTP on {selection['option_type']} {selection['strike']:.0f} — illiquid"}
    if volume < 5:
        return {"approved": False,
                "reason": f"Volume {volume} lots < 5 — insufficient liquidity at {selection['strike']:.0f}"}

    # Bid-ask spread > 3% of LTP = too wide (slippage kills edge)
    if bid > 0 and ask > 0:
        spread_pct = (ask - bid) / ltp * 100
        if spread_pct > 3.0:
            return {"approved": False,
                    "reason": f"Bid-ask spread {spread_pct:.1f}% > 3% — slippage too high (bid {bid} / ask {ask})"}

    # ── Daily loss limit ───────────────────────────────────────────────────────
    loss_today = _today_realised_loss()
    loss_limit = CAPITAL * DAILY_LOSS_LIMIT_PCT / 100
    if loss_today >= loss_limit:
        return {"approved": False,
                "reason": f"Daily loss limit hit: ₹{loss_today:,.0f} ≥ ₹{loss_limit:,.0f} ({DAILY_LOSS_LIMIT_PCT}% cap)"}

    # ── Sizing ─────────────────────────────────────────────────────────────────
    max_risk_rs     = CAPITAL * MAX_RISK_PCT / 100
    sl_premium      = round(ltp * 0.50, 1)          # 50% of premium
    sl_cost_per_lot = sl_premium * lot

    qty = max(1, int(max_risk_rs / sl_cost_per_lot))

    # Cap so total new loss stays within remaining daily capacity
    remaining = max(0.0, loss_limit - loss_today)
    qty = min(qty, max(1, int(remaining / sl_cost_per_lot)))

    max_loss_rs = round(qty * sl_cost_per_lot, 2)
    tp_premium  = round(ltp * 2.0, 1)               # 2× SL in premium terms

    risk_pct = max_loss_rs / CAPITAL * 100
    reason = (
        f"APPROVED — {qty} lot(s) × {lot} units @ ₹{ltp:.1f} | "
        f"SL ₹{sl_premium:.1f} / TP ₹{tp_premium:.1f} per unit | "
        f"Max risk ₹{max_loss_rs:,.0f} ({risk_pct:.2f}% of capital) | "
        f"Daily used ₹{loss_today:,.0f} / limit ₹{loss_limit:,.0f}"
    )

    return {
        "approved":    True,
        "qty":         qty,
        "ltp":         ltp,
        "lot":         lot,
        "max_loss_rs": max_loss_rs,
        "sl_premium":  sl_premium,
        "tp_premium":  tp_premium,
        "reason":      reason,
    }
