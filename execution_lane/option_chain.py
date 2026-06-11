"""
Scrip master download, instrument lookup, and live option chain assembly.

Chain data format (used throughout the pipeline):
  {
    "name":    str,
    "expiry":  date,
    "atm":     float,
    "strikes": {
      float_strike: {
        "lot": int,
        "CE":  {"token": str, "symbol": str, "ltp": float,
                "oi": int, "oi_change": int, "volume": int},
        "PE":  { same },
      }
    }
  }
"""
import json
import time
import requests
from datetime import datetime, date
from typing import Optional

from SmartApi import SmartConnect

from config import (
    MCX_EXCHANGE,
    FULL_NAME, MINI_NAME, FULL_LOT, MINI_LOT,
    SCRIP_MASTER_URL, SCRIP_CACHE_FILE, SCRIP_CACHE_HOURS, LOG_DIR,
)


# ─── Scrip master ──────────────────────────────────────────────────────────────

def load_scrip_master() -> list:
    if SCRIP_CACHE_FILE.exists():
        try:
            cached = json.loads(SCRIP_CACHE_FILE.read_text())
            if time.time() - cached["ts"] < SCRIP_CACHE_HOURS * 3600:
                return cached["data"]
        except Exception:
            pass
    print("  Downloading scrip master... ", end="", flush=True)
    resp = requests.get(SCRIP_MASTER_URL, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    SCRIP_CACHE_FILE.write_text(json.dumps({"ts": time.time(), "data": data}))
    print(f"done ({len(data):,} instruments)")
    return data


def _parse_expiry(raw: str) -> Optional[date]:
    for fmt in ("%d%b%Y", "%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip().upper(), fmt).date()
        except ValueError:
            continue
    return None


# ─── Instrument lookup ─────────────────────────────────────────────────────────

def get_option_instruments(name: str) -> dict:
    """
    Returns {expiry_date: {strike(float): {"lot": int, "CE": {...}, "PE": {...}}}}
    for active MCX option expiries only.
    """
    master = load_scrip_master()
    today  = date.today()
    chain: dict = {}

    for item in master:
        if item.get("exch_seg") != MCX_EXCHANGE:
            continue
        if item.get("name", "").upper() != name.upper():
            continue
        if item.get("instrumenttype") != "OPTFUT":
            continue

        exp = _parse_expiry(item.get("expiry", ""))
        if exp is None or exp < today:
            continue

        sym = item.get("symbol", "")
        if "CE" in sym:
            opt_type = "CE"
        elif "PE" in sym:
            opt_type = "PE"
        else:
            continue

        try:
            # MCX scrip master stores strikes as actual_strike × 100 (paise format).
            # Divide by 100 to recover the per-barrel rupee strike price.
            strike = float(item["strike"]) / 100.0
        except (KeyError, ValueError):
            continue

        default_lot = FULL_LOT if name.upper() == FULL_NAME.upper() else MINI_LOT
        lot   = int(item.get("lotsize") or default_lot)
        token = item.get("token", "")

        chain.setdefault(exp, {}).setdefault(strike, {"lot": lot})
        chain[exp][strike][opt_type] = {"token": token, "symbol": sym}

    return chain


def get_current_expiry(name: str) -> tuple[date, dict]:
    """Returns (nearest_expiry_date, strike_dict)."""
    all_expiries = get_option_instruments(name)
    if not all_expiries:
        raise RuntimeError(f"No active option instruments found for {name} on MCX")
    nearest = sorted(all_expiries.keys())[0]
    return nearest, all_expiries[nearest]


def get_futures_token(name: str) -> tuple[str, str]:
    """Returns (symbol, token) for the nearest front-month futures contract."""
    master = load_scrip_master()
    today  = date.today()
    candidates = []
    for item in master:
        if item.get("exch_seg") != MCX_EXCHANGE:
            continue
        if item.get("name", "").upper() != name.upper():
            continue
        if item.get("instrumenttype") != "FUTCOM":
            continue
        exp = _parse_expiry(item.get("expiry", ""))
        if exp and exp >= today:
            candidates.append((exp, item.get("symbol", ""), item.get("token", "")))
    if not candidates:
        return "", ""
    candidates.sort(key=lambda x: x[0])
    _, sym, tok = candidates[0]
    return sym, tok


# ─── OI snapshot (for intraday OI-change computation) ─────────────────────────

_OI_SNAPSHOT_FILE = LOG_DIR / f"oi_snapshot_{date.today():%Y%m%d}.json"


def _load_oi_snapshot() -> dict:
    if _OI_SNAPSHOT_FILE.exists():
        try:
            return json.loads(_OI_SNAPSHOT_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_oi_snapshot(snapshot: dict):
    try:
        _OI_SNAPSHOT_FILE.write_text(json.dumps(snapshot))
    except Exception:
        pass


# ─── Market data ──────────────────────────────────────────────────────────────

def _fetch_quotes(obj: SmartConnect, tokens: list, exchange: str = MCX_EXCHANGE) -> dict:
    """Batch-fetches FULL market data. Returns {token: data_dict}."""
    result = {}
    for i in range(0, len(tokens), 50):
        batch = tokens[i:i + 50]
        try:
            resp = obj.getMarketData(mode="FULL", exchangeTokens={exchange: batch})
            if resp and resp.get("status"):
                for item in (resp.get("data") or {}).get("fetched", []):
                    result[item["symbolToken"]] = item
        except Exception as e:
            print(f"\n  [warn] market data batch error: {e}")
    return result


def get_underlying_price(obj: SmartConnect, name: str = MINI_NAME) -> float:
    """Fetch front-month futures LTP as underlying proxy."""
    _, tok = get_futures_token(name)
    if not tok:
        return 0.0
    quotes = _fetch_quotes(obj, [tok])
    q = quotes.get(tok, {})
    return float(q.get("ltp") or q.get("close") or 0)


# ─── Full chain assembly ───────────────────────────────────────────────────────

def build_live_chain(obj: SmartConnect, name: str, underlying: float = 0.0) -> dict:
    """
    Assembles the full live chain dict.
    OI change is computed vs a daily snapshot file — first run of the day
    saves the baseline; subsequent runs diff against it.
    """
    expiry, raw_chain = get_current_expiry(name)

    all_tokens = []
    for sd in raw_chain.values():
        for ot in ("CE", "PE"):
            if ot in sd:
                all_tokens.append(sd[ot]["token"])

    quotes = _fetch_quotes(obj, all_tokens)

    # OI snapshot for intraday change
    oi_snapshot = _load_oi_snapshot()
    new_snapshot = dict(oi_snapshot)
    snapshot_is_new = not oi_snapshot

    # Determine ATM
    sorted_strikes = sorted(raw_chain.keys())
    atm = (min(sorted_strikes, key=lambda s: abs(s - underlying))
           if underlying > 0 else sorted_strikes[len(sorted_strikes) // 2])

    live_strikes: dict = {}
    for strike, sd in raw_chain.items():
        entry: dict = {"lot": sd.get("lot", MINI_LOT)}
        for ot in ("CE", "PE"):
            if ot not in sd:
                continue
            tok = sd[ot]["token"]
            sym = sd[ot]["symbol"]
            q   = quotes.get(tok, {})

            # API field is "opnInterest" (not "openInterest")
            oi = int(q.get("opnInterest") or 0)

            # Compute OI change vs daily snapshot
            if snapshot_is_new:
                new_snapshot[tok] = oi
                oi_chg = 0
            else:
                oi_chg = oi - oi_snapshot.get(tok, oi)

            # Bid/ask from depth (top of book)
            depth = q.get("depth", {})
            bid = float((depth.get("buy") or [{}])[0].get("price") or 0)
            ask = float((depth.get("sell") or [{}])[0].get("price") or 0)

            entry[ot] = {
                "token":     tok,
                "symbol":    sym,
                "ltp":       float(q.get("ltp") or q.get("close") or 0),
                "oi":        oi,
                "oi_change": oi_chg,
                "volume":    int(q.get("tradeVolume") or q.get("volume") or 0),
                "bid":       bid,
                "ask":       ask,
            }
        live_strikes[strike] = entry

    if snapshot_is_new:
        _save_oi_snapshot(new_snapshot)

    return {"name": name, "expiry": expiry, "atm": atm, "strikes": live_strikes}
