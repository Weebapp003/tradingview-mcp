# -*- coding: utf-8 -*-
import sys
import logging
sys.stdout.reconfigure(encoding="utf-8")
logging.disable(logging.INFO)  # silence SmartAPI's chatty logger

"""
Execution lane entry point.

Usage (paper, default):
  python run.py --bias short --conviction 6 --stop 9013 --targets 8679,8543

Usage (live):
  python run.py --bias short --conviction 6 --stop 9013 --targets 8679,8543 --paper false

Pipeline:
  Auth → underlying price → full chain (OI analysis) → analyze →
  mini chain (execution) → strike selection → risk gate → order
"""
import argparse
import sys

import auth
import option_chain as oc
import chain_analyzer as ca
import strike_selector as ss
import risk_gate as rg
import order_manager as om
from config import FULL_NAME, MINI_NAME, PAPER, ATM_WINGS


# ─── Display helpers ───────────────────────────────────────────────────────────

_SEP = "═" * 66


def _print_analysis(analysis: dict):
    pcr_tag = ("bearish↑" if analysis["pcr_full"] > 1.3 else
               "bullish↓" if analysis["pcr_full"] < 0.7 else "neutral")
    walls   = analysis["oi_walls"]
    oi_chg  = analysis["oi_chg"]
    skew    = analysis["skew"]

    print(f"\n{_SEP}")
    print(f"  CHAIN ANALYSIS  [{analysis['expiry']}]  "
          f"underlying={analysis['underlying']:.0f}  ATM={analysis['atm']:.0f}")
    print(_SEP)
    print(f"  PCR (full chain):  {analysis['pcr_full']:.3f}  [{pcr_tag}]")
    print(f"  PCR (ATM ± 5):     {analysis['pcr_atm5']:.3f}")
    print(f"  Max pain:          {analysis['max_pain']:.0f}  "
          f"(spot delta {analysis['max_pain'] - analysis['underlying']:+.0f})")
    ce_w = "  ".join(f"{w['strike']:.0f}({w['oi']:,})" for w in walls["ce_walls"])
    pe_w = "  ".join(f"{w['strike']:.0f}({w['oi']:,})" for w in walls["pe_walls"])
    print(f"  CE walls (resist): {ce_w}")
    print(f"  PE walls (support): {pe_w}")
    print(f"  OI flow:   CE +{oi_chg['ce_added']:,}/-{oi_chg['ce_shed']:,}  "
          f"PE +{oi_chg['pe_added']:,}/-{oi_chg['pe_shed']:,}  → {oi_chg['net_lean']}")
    if skew:
        print(f"  IV skew:   PE{skew['pe_strike']:.0f}=₹{skew['pe_ltp']:.1f}  "
              f"CE{skew['ce_strike']:.0f}=₹{skew['ce_ltp']:.1f}  "
              f"ratio={skew['skew_ratio']}  [{skew['lean']}]")

    # ATM strip table
    print()
    hdr = (f"  {'STRIKE':>8}  {'Δ':>4}  "
           f"{'CE_LTP':>7}  {'CE_OI':>8}  {'ΔOICE':>7}  {'CEVOL':>6}  "
           f"{'PE_LTP':>7}  {'PE_OI':>8}  {'ΔOIPE':>7}  {'PEVOL':>6}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for row in analysis["strip"]:
        marker = " ◄" if row["delta"] == "ATM" else ""
        print(
            f"  {row['strike']:>8.0f}  {row['delta']:>4}  "
            f"{row['CE_LTP']:>7.1f}  {row['CE_OI']:>8,}  {row['CE_OI_CHG']:>+7,}  {row['CE_VOL']:>6,}  "
            f"{row['PE_LTP']:>7.1f}  {row['PE_OI']:>8,}  {row['PE_OI_CHG']:>+7,}  {row['PE_VOL']:>6,}"
            f"{marker}"
        )
    print(_SEP)


def _print_selection(sel: dict):
    print(f"\n  STRIKE SELECTION ({sel.get('tradingsymbol', '')})")
    print(f"  {'─'*62}")
    if sel["action"]:
        print(f"  Action:      {sel['action']} {sel['option_type']} {sel['strike']:.0f}")
        bid, ask = sel.get("bid", 0), sel.get("ask", 0)
        spread_pct = (ask - bid) / sel['ltp'] * 100 if sel['ltp'] and bid and ask else 0
        print(f"  LTP:         ₹{sel['ltp']:.1f}  bid {bid:.1f} / ask {ask:.1f}  "
              f"spread {spread_pct:.2f}%")
        print(f"  OI:          {sel['oi']:,}   Volume: {sel['volume']:,}   Lot: {sel['lot']}")
        print(f"  Rationale:   {sel['rationale']}")
    else:
        print(f"  {sel['rationale']}")
    if sel["conflicts"]:
        print(f"\n  ⚠  CHAIN CONFLICTS ({len(sel['conflicts'])}):")
        for c in sel["conflicts"]:
            print(f"     • {c}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CRUDEOIL Options Execution Lane")
    parser.add_argument("--bias",       required=True, choices=["long", "short", "neutral"])
    parser.add_argument("--conviction", type=int, default=5)
    parser.add_argument("--stop",       type=float, required=True,
                        help="Underlying hard stop level from research lane")
    parser.add_argument("--targets",    required=True,
                        help="Comma-separated underlying targets e.g. 8679,8543")
    parser.add_argument("--paper",      default=str(PAPER),
                        help="true/false — overrides PAPER env var")
    args = parser.parse_args()

    paper      = args.paper.lower() != "false"
    bias       = args.bias
    conviction = args.conviction
    stop_level = args.stop
    targets    = [float(t) for t in args.targets.split(",")]

    print(f"\n{_SEP}")
    print(f"  EXECUTION LANE  |  bias={bias.upper()}  conviction={conviction}/10  "
          f"{'[PAPER]' if paper else '[LIVE ⚠]'}")
    print(f"  Stop: {stop_level:.0f}  |  "
          f"Targets: {' → '.join(f'{t:.0f}' for t in targets)}")
    print(_SEP)

    # 1 ── Auth
    print("\n  [1/6] Authenticating SmartAPI...", end="  ", flush=True)
    obj = auth.get_session()
    print("ok")

    # 2 ── Underlying price
    print(f"  [2/6] Fetching {MINI_NAME} front-month futures price...", end="  ", flush=True)
    underlying = oc.get_underlying_price(obj, MINI_NAME)
    print(f"₹{underlying:.1f}" if underlying else "FAILED (chain ATM may be inaccurate)")

    # 3 ── Full chain (analysis)
    print(f"  [3/6] Building {FULL_NAME} option chain (OI analysis)...", end="  ", flush=True)
    full_chain = oc.build_live_chain(obj, FULL_NAME, underlying)
    print(f"expiry={full_chain['expiry']}  strikes={len(full_chain['strikes'])}")

    # 4 ── Analyze
    print(f"  [4/6] Analyzing chain...", end="  ", flush=True)
    analysis = ca.analyze(full_chain, underlying, wings=ATM_WINGS)
    print("ok")
    _print_analysis(analysis)

    # 5 ── Mini chain + strike selection
    print(f"\n  [5/6] Building {MINI_NAME} mini chain + selecting strike...", end="  ", flush=True)
    mini_chain = oc.build_live_chain(obj, MINI_NAME, underlying)
    selection  = ss.select(analysis, mini_chain, bias, conviction)
    print("ok")
    _print_selection(selection)

    # 6 ── Risk gate
    print(f"\n  [6/6] Risk gate check...")
    risk     = rg.check(selection, underlying, stop_level)
    approved = risk.get("approved", False)
    status   = "✓ APPROVED" if approved else "✗ BLOCKED"
    print(f"  {status}: {risk['reason']}")

    if not approved:
        print(f"\n  [HALT] Trade blocked. No order placed.\n")
        sys.exit(0)

    # ── Execute ───────────────────────────────────────────────────────────────
    print(f"\n  Executing ({'PAPER' if paper else 'LIVE'} mode)...")
    result = om.execute(obj, selection, risk, paper=paper)

    icon = "✓" if result["success"] else "✗"
    print(f"\n  {icon} {result['detail']}")
    if result.get("order_id"):
        print(f"  Order ID: {result['order_id']}")
    print(f"  Log: {om._TRADE_LOG}\n")


if __name__ == "__main__":
    main()
