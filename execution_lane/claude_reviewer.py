# -*- coding: utf-8 -*-
"""
Claude API trade reviewer.

Before every trade execution, sends signal + chain context to Claude Haiku.
Claude returns EXECUTE or SKIP with a one-line reason.

Uses claude-haiku-4-5 (fast, cheap ~Rs0.08/call) for binary decisions.
"""
import json
from pathlib import Path
from datetime import date

import anthropic
from config import CLAUDE_API_KEY, LOG_DIR

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    return _client


def _load_recent_outcomes(n: int = 5) -> list:
    """Load last n closed trades for context."""
    results = []
    for f in sorted(LOG_DIR.glob("outcomes_*.jsonl"), reverse=True)[:3]:
        try:
            lines = f.read_text(encoding="utf-8").strip().splitlines()
            for line in reversed(lines):
                if len(results) >= n:
                    break
                results.append(json.loads(line))
        except Exception:
            continue
    return results[:n]


def _format_factors(factors: dict, weights: dict) -> str:
    lines = []
    bar = lambda s: "+" if s > 0 else ("-" if s < 0 else "0")
    for k, v in factors.items():
        w = weights.get(k, 1.0)
        lines.append(f"  {k:<12} [{bar(v['score'])}]  weight={w:.2f}  {v['label']}")
    return "\n".join(lines)


def review(signal: dict, analysis: dict) -> tuple[str, str]:
    """
    Ask Claude to approve or veto the trade.

    Returns:
      decision: "EXECUTE" or "SKIP"
      reason:   one-sentence explanation
    """
    if not CLAUDE_API_KEY:
        return "EXECUTE", "No Claude API key — auto-approved"

    weights      = signal.get("weights_snap", {})
    recent       = _load_recent_outcomes(5)
    recent_lines = []
    for t in recent:
        outcome = t.get("outcome", "OPEN")
        pnl     = t.get("pnl", 0)
        recent_lines.append(
            f"  {outcome:<5}  {t.get('option',''):<15}  "
            f"entry Rs{t.get('entry_ltp',0):.0f}  "
            f"exit Rs{t.get('exit_ltp',0):.0f}  "
            f"P&L Rs{pnl:+.0f}"
        )

    walls = analysis.get("oi_walls", {})
    ce_w  = walls.get("ce_walls", [{}])[0].get("strike", "?")
    pe_w  = walls.get("pe_walls", [{}])[0].get("strike", "?")

    prompt = f"""You are a crude oil options trading risk manager for MCX CRUDEOILM.
Review this trade signal and decide: EXECUTE or SKIP.

SIGNAL
  Bias:        {signal['bias'].upper()}
  Score:       {signal['score']:+.3f} (range -1 to +1, threshold +-0.375)
  Conviction:  {signal['conviction']}/10
  Underlying:  Rs{signal['underlying']:.0f}
  RSI:         {signal.get('rsi', 0):.1f}
  VWAP:        Rs{signal.get('vwap', 0):.0f}
  Vol confirm: {signal.get('vol_confirm', False)}

PRICE ACTION FACTORS (learned weights)
{_format_factors(signal.get('pa_factors', {}), weights)}

CHAIN FACTORS (learned weights)
{_format_factors(signal.get('ch_factors', {}), weights)}

CHAIN CONTEXT
  PCR:         {analysis.get('pcr_full', 0):.3f}
  Max pain:    Rs{analysis.get('max_pain', 0):.0f}  (spot delta {analysis.get('max_pain', 0) - signal['underlying']:+.0f})
  CE wall:     Rs{ce_w}
  PE wall:     Rs{pe_w}
  OI flow:     {analysis.get('oi_chg', {}).get('net_lean', '?')}

RECENT TRADE HISTORY (last 5)
{chr(10).join(recent_lines) if recent_lines else "  No closed trades yet"}

RULES
- SKIP if score is borderline (0.375-0.45) AND recent trades show 2+ consecutive losses
- SKIP if OI flow contradicts bias strongly
- SKIP if max pain delta > 200 pts against trade direction
- EXECUTE if score > 0.5 and chain confirms
- EXECUTE if recent win rate > 50% and signal is clean

Reply with EXACTLY:
Line 1: EXECUTE  or  SKIP
Line 2: One sentence reason (max 15 words)"""

    try:
        msg = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            messages=[{"role": "user", "content": prompt}],
        )
        raw   = msg.content[0].text.strip()
        lines = raw.splitlines()
        decision = "EXECUTE" if "EXECUTE" in lines[0].upper() else "SKIP"
        reason   = lines[1].strip() if len(lines) > 1 else raw
        return decision, reason
    except Exception as e:
        return "EXECUTE", f"Claude unavailable ({e}) — auto-approved"
