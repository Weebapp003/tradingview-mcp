"""
Strike selection + bias↔chain conflict detection.

For a SHORT bias → BUY PE (defined-risk directional).
For a LONG  bias → BUY CE.
Neutral         → no trade.

Selects the best OTM-or-ATM strike from the MINI (execution) chain,
using OI/skew/walls from the FULL (analysis) chain via `analysis`.
"""


def select(analysis: dict, exec_chain: dict, bias: str, conviction: int) -> dict:
    if bias == "neutral":
        return {"bias": bias, "action": None,
                "rationale": "Neutral bias — no trade", "conflicts": []}

    pcr        = analysis["pcr_full"]
    max_pain   = analysis["max_pain"]
    atm        = analysis["atm"]
    underlying = analysis["underlying"]
    walls      = analysis["oi_walls"]
    oi_chg     = analysis["oi_chg"]

    # ── Chain lean ─────────────────────────────────────────────────────────────
    chain_lean = ("bullish" if pcr < 0.7 else
                  "bearish" if pcr > 1.3 else "neutral")

    mp_gap  = max_pain - underlying
    mp_lean = ("bullish" if mp_gap > 100 else
               "bearish" if mp_gap < -100 else "neutral")

    ce_wall = walls["ce_walls"][0]["strike"] if walls["ce_walls"] else 0.0
    pe_wall = walls["pe_walls"][0]["strike"] if walls["pe_walls"] else 0.0

    # ── Conflict detection ─────────────────────────────────────────────────────
    conflicts = []
    if bias == "short":
        if chain_lean == "bullish":
            conflicts.append(
                f"PCR {pcr:.2f} < 0.7 → chain leans BULLISH — contradicts SHORT bias")
        if mp_lean == "bullish":
            conflicts.append(
                f"Max pain {max_pain:.0f} is {mp_gap:+.0f} above spot — gravity pulls UP")
        if oi_chg["net_lean"] == "bullish":
            conflicts.append(
                "OI flow: CE shedding + PE adding → potential squeeze risk")
    elif bias == "long":
        if chain_lean == "bearish":
            conflicts.append(
                f"PCR {pcr:.2f} > 1.3 → chain leans BEARISH — contradicts LONG bias")
        if mp_lean == "bearish":
            conflicts.append(
                f"Max pain {max_pain:.0f} is {mp_gap:+.0f} below spot — gravity pulls DOWN")

    # ── Strike selection from exec (MINI) chain ────────────────────────────────
    opt_type = "PE" if bias == "short" else "CE"
    exec_strikes = sorted(exec_chain["strikes"].keys())

    # PE candidates: at or below ATM (sorted highest first for slight OTM preference)
    # CE candidates: at or above ATM (sorted lowest first)
    if bias == "short":
        candidates = sorted([s for s in exec_strikes if s <= atm], reverse=True)
    else:
        candidates = sorted([s for s in exec_strikes if s >= atm])

    if not candidates:
        candidates = exec_strikes  # fallback if ATM bracket is empty

    # Pick first candidate with LTP ≥ 5 and volume ≥ 5 (liquid enough to trade)
    chosen = None
    for s in candidates[:5]:
        sd = exec_chain["strikes"].get(s, {}).get(opt_type, {})
        if sd.get("ltp", 0) >= 5 and sd.get("volume", 0) >= 5:
            chosen = s
            break
    # Fallback: any candidate with positive LTP
    if chosen is None:
        for s in candidates:
            if exec_chain["strikes"].get(s, {}).get(opt_type, {}).get("ltp", 0) > 0:
                chosen = s
                break
    if chosen is None:
        chosen = candidates[0] if candidates else exec_strikes[len(exec_strikes) // 2]

    sd_data = exec_chain["strikes"].get(chosen, {}).get(opt_type, {})
    lot     = exec_chain["strikes"].get(chosen, {}).get("lot", 10)

    rationale = (
        f"{bias.upper()} bias → BUY {opt_type} | "
        f"Strike {chosen:.0f} ({chosen - atm:+.0f} from ATM {atm:.0f}) | "
        f"CE wall {ce_wall:.0f} | PE wall {pe_wall:.0f} | "
        f"PCR {pcr:.2f} ({chain_lean}) | max-pain {max_pain:.0f} ({mp_lean}) | "
        f"OI-flow {oi_chg['net_lean']}"
    )

    return {
        "bias":          bias,
        "action":        "BUY",
        "option_type":   opt_type,
        "strike":        chosen,
        "token":         sd_data.get("token", ""),
        "tradingsymbol": sd_data.get("symbol", ""),
        "ltp":           sd_data.get("ltp", 0),
        "bid":           sd_data.get("bid", 0),
        "ask":           sd_data.get("ask", 0),
        "volume":        sd_data.get("volume", 0),
        "oi":            sd_data.get("oi", 0),
        "lot":           lot,
        "chain_lean":    chain_lean,
        "mp_lean":       mp_lean,
        "ce_wall":       ce_wall,
        "pe_wall":       pe_wall,
        "rationale":     rationale,
        "conflicts":     conflicts,
    }
