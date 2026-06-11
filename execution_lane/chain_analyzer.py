"""
Chain analysis: PCR, max pain, OI walls, OI-change flow, IV skew proxy, ATM strip.
All functions accept the chain dict produced by option_chain.build_live_chain().
"""


def compute_pcr(chain: dict, atm: float = 0.0, wing: int = 0) -> float:
    """Total PE OI / Total CE OI. wing > 0 limits scope to ATM ± wing strikes."""
    strikes = sorted(chain["strikes"].keys())
    if wing > 0 and atm > 0:
        idx     = min(range(len(strikes)), key=lambda i: abs(strikes[i] - atm))
        strikes = strikes[max(0, idx - wing): idx + wing + 1]
    pe_oi = sum(chain["strikes"][s].get("PE", {}).get("oi", 0) for s in strikes)
    ce_oi = sum(chain["strikes"][s].get("CE", {}).get("oi", 0) for s in strikes)
    return round(pe_oi / ce_oi, 3) if ce_oi else 0.0


def compute_max_pain(chain: dict) -> float:
    """Strike at which total option-buyer value (pain to sellers) is minimum."""
    strikes = sorted(chain["strikes"].keys())
    best_strike, best_val = strikes[0], float("inf")
    for k in strikes:
        pain = 0.0
        for s in strikes:
            sd  = chain["strikes"][s]
            lot = sd.get("lot", 10)
            pain += max(0.0, k - s) * sd.get("CE", {}).get("oi", 0) * lot
            pain += max(0.0, s - k) * sd.get("PE", {}).get("oi", 0) * lot
        if pain < best_val:
            best_val, best_strike = pain, k
    return best_strike


def oi_walls(chain: dict, top_n: int = 3) -> dict:
    """Top-N CE OI strikes (resistance) and PE OI strikes (support)."""
    sdata = chain["strikes"]
    ce = sorted(
        [(s, sdata[s].get("CE", {}).get("oi", 0)) for s in sdata if "CE" in sdata[s]],
        key=lambda x: x[1], reverse=True,
    )[:top_n]
    pe = sorted(
        [(s, sdata[s].get("PE", {}).get("oi", 0)) for s in sdata if "PE" in sdata[s]],
        key=lambda x: x[1], reverse=True,
    )[:top_n]
    return {
        "ce_walls": [{"strike": s, "oi": oi} for s, oi in ce],
        "pe_walls": [{"strike": s, "oi": oi} for s, oi in pe],
    }


def oi_change_flow(chain: dict) -> dict:
    """
    Summarises net OI direction across all strikes.
    CE writing up + PE unwinding → bearish chain.
    PE writing up + CE unwinding → bullish chain.
    """
    ce_add = ce_shed = pe_add = pe_shed = 0
    for sd in chain["strikes"].values():
        ce_chg = sd.get("CE", {}).get("oi_change", 0)
        pe_chg = sd.get("PE", {}).get("oi_change", 0)
        if ce_chg > 0: ce_add  += ce_chg
        else:          ce_shed += abs(ce_chg)
        if pe_chg > 0: pe_add  += pe_chg
        else:          pe_shed += abs(pe_chg)

    if ce_add > ce_shed and pe_shed > pe_add:
        lean = "bearish"   # CE writers active, PE unwinding
    elif pe_add > pe_shed and ce_shed > ce_add:
        lean = "bullish"   # PE writers active, CE unwinding
    else:
        lean = "mixed"

    return {
        "ce_added": ce_add, "ce_shed": ce_shed,
        "pe_added": pe_add, "pe_shed": pe_shed,
        "net_lean": lean,
    }


def iv_skew(chain: dict, atm: float, wing: int = 2) -> dict | None:
    """
    Proxy skew via equidistant OTM PE vs CE LTP.
    skew_ratio > 1 → put skew (downside fear).
    """
    strikes = sorted(chain["strikes"].keys())
    if not strikes:
        return None
    idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - atm))
    lo, hi = idx - wing, idx + wing
    if lo < 0 or hi >= len(strikes):
        return None
    pe_ltp = chain["strikes"][strikes[lo]].get("PE", {}).get("ltp", 0)
    ce_ltp = chain["strikes"][strikes[hi]].get("CE", {}).get("ltp", 0)
    if ce_ltp == 0:
        return None
    return {
        "pe_strike": strikes[lo], "pe_ltp": pe_ltp,
        "ce_strike": strikes[hi], "ce_ltp": ce_ltp,
        "skew_ratio": round(pe_ltp / ce_ltp, 2),
        "lean": "put-skew (downside fear)" if pe_ltp > ce_ltp else "call-skew (upside greed)",
    }


def atm_strip(chain: dict, atm: float, wing: int = 5) -> list:
    """ATM ± wing strikes with full OI + LTP data."""
    strikes = sorted(chain["strikes"].keys())
    idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - atm))
    lo  = max(0, idx - wing)
    hi  = min(len(strikes) - 1, idx + wing)
    rows = []
    for i in range(lo, hi + 1):
        s  = strikes[i]
        sd = chain["strikes"][s]
        tag = "ATM" if i == idx else (f"+{i - idx}" if i > idx else str(i - idx))
        rows.append({
            "strike":    s,
            "delta":     tag,
            "CE_LTP":    sd.get("CE", {}).get("ltp", 0),
            "CE_OI":     sd.get("CE", {}).get("oi", 0),
            "CE_OI_CHG": sd.get("CE", {}).get("oi_change", 0),
            "CE_VOL":    sd.get("CE", {}).get("volume", 0),
            "PE_LTP":    sd.get("PE", {}).get("ltp", 0),
            "PE_OI":     sd.get("PE", {}).get("oi", 0),
            "PE_OI_CHG": sd.get("PE", {}).get("oi_change", 0),
            "PE_VOL":    sd.get("PE", {}).get("volume", 0),
        })
    return rows


def analyze(full_chain: dict, underlying: float, wings: int = 5) -> dict:
    """Master analysis dict — source of truth for strike_selector and risk_gate."""
    atm = full_chain.get("atm", underlying)
    return {
        "underlying": underlying,
        "expiry":     str(full_chain["expiry"]),
        "atm":        atm,
        "pcr_full":   compute_pcr(full_chain),
        "pcr_atm5":   compute_pcr(full_chain, atm=atm, wing=5),
        "max_pain":   compute_max_pain(full_chain),
        "oi_walls":   oi_walls(full_chain),
        "oi_chg":     oi_change_flow(full_chain),
        "skew":       iv_skew(full_chain, atm, wing=2),
        "strip":      atm_strip(full_chain, atm, wing=wings),
    }
