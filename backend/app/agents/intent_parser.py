"""IntentParser — extracts structured research parameters from vague user requests.

Combines rule-based keyword matching with optional LLM disambiguation.
Returns a ResearchIntent with market, timeframe, style, risk tolerance, etc.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ResearchIntent:
    market: str = "crypto"
    timeframe: str = "1h"
    style: str = "intraday"
    risk_tolerance: str = "medium"
    target_metrics: Dict[str, float] = field(default_factory=lambda: {
        "min_sharpe": 1.0, "max_dd": -0.30, "min_pf": 1.2, "min_trades": 50,
    })
    constraints: List[str] = field(default_factory=list)
    raw_request: str = ""
    confidence: float = 0.5
    clarification_needed: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Market={self.market}, TF={self.timeframe}, Style={self.style}, "
            f"Risk={self.risk_tolerance}, Targets={self.target_metrics}"
        )


# ── Keyword maps ────────────────────────────────────────────────────────

_MARKET_KEYWORDS = {
    "nifty": "nifty", "banknifty": "banknifty", "bank nifty": "banknifty",
    "nifty50": "nifty", "sensex": "sensex",
    "btc": "crypto", "bitcoin": "crypto", "eth": "crypto", "ethereum": "crypto",
    "crypto": "crypto", "cryptocurrency": "crypto",
    "forex": "forex", "fx": "forex", "eurusd": "forex", "gbpusd": "forex",
    "xauusd": "forex", "gold": "forex", "usdjpy": "forex",
    "stock": "equities", "equity": "equities", "equities": "equities",
    "spy": "equities", "aapl": "equities", "nasdaq": "equities",
    "futures": "futures", "crude": "futures", "oil": "futures",
}

_TIMEFRAME_KEYWORDS = {
    "1m": "1m", "1min": "1m", "1 min": "1m", "1 minute": "1m",
    "5m": "5m", "5min": "5m", "5 min": "5m", "5 minute": "5m",
    "15m": "15m", "15min": "15m", "15 min": "15m",
    "30m": "30m", "30min": "30m",
    "1h": "1h", "1hr": "1h", "1 hour": "1h", "hourly": "1h",
    "4h": "4h", "4hr": "4h", "4 hour": "4h",
    "1d": "1d", "daily": "1d", "1 day": "1d",
    "1w": "1w", "weekly": "1w",
}

_STYLE_KEYWORDS = {
    "scalp": "scalping", "scalping": "scalping",
    "intraday": "intraday", "day trade": "intraday", "day trading": "intraday",
    "swing": "swing", "swing trade": "swing", "swing trading": "swing",
    "positional": "positional", "position": "positional", "long term": "positional",
}

_RISK_KEYWORDS = {
    "conservative": "low", "low risk": "low", "safe": "low", "minimal risk": "low",
    "moderate": "medium", "medium risk": "medium", "balanced": "medium",
    "aggressive": "high", "high risk": "high", "risky": "high", "yolo": "high",
}

# Style → default timeframe mapping
_STYLE_TF_DEFAULTS = {
    "scalping": "1m", "intraday": "5m", "swing": "4h", "positional": "1d",
}

# Risk → target metric adjustments
_RISK_TARGETS = {
    "low":    {"min_sharpe": 1.5, "max_dd": -0.15, "min_pf": 1.5, "min_trades": 50},
    "medium": {"min_sharpe": 1.0, "max_dd": -0.25, "min_pf": 1.2, "min_trades": 50},
    "high":   {"min_sharpe": 0.5, "max_dd": -0.40, "min_pf": 1.0, "min_trades": 30},
}


class IntentParser:
    """Parse user request into a structured ResearchIntent."""

    def parse(self, user_text: str) -> ResearchIntent:
        lower = user_text.lower().strip()
        intent = ResearchIntent(raw_request=user_text)
        matched = 0

        # Market detection
        for kw, market in _MARKET_KEYWORDS.items():
            if kw in lower:
                intent.market = market
                matched += 1
                break

        # Timeframe detection
        for kw, tf in _TIMEFRAME_KEYWORDS.items():
            if kw in lower:
                intent.timeframe = tf
                matched += 1
                break

        # Style detection
        for kw, style in _STYLE_KEYWORDS.items():
            if kw in lower:
                intent.style = style
                matched += 1
                break

        # Risk detection
        for kw, risk in _RISK_KEYWORDS.items():
            if kw in lower:
                intent.risk_tolerance = risk
                matched += 1
                break

        # Apply smart defaults
        if intent.timeframe == "1h" and intent.style != "intraday":
            intent.timeframe = _STYLE_TF_DEFAULTS.get(intent.style, "1h")

        intent.target_metrics = _RISK_TARGETS.get(intent.risk_tolerance, _RISK_TARGETS["medium"]).copy()

        # Extract explicit numeric targets from text
        sharpe_match = re.search(r"sharpe\s*[>:=]\s*([\d.]+)", lower)
        if sharpe_match:
            intent.target_metrics["min_sharpe"] = float(sharpe_match.group(1))

        dd_match = re.search(r"(?:drawdown|dd)\s*[<:=]\s*([\d.]+)%?", lower)
        if dd_match:
            val = float(dd_match.group(1))
            intent.target_metrics["max_dd"] = -(val / 100 if val > 1 else val)

        # Constraints
        if any(w in lower for w in ["no overnight", "close eod", "exit by close"]):
            intent.constraints.append("no_overnight_holds")
        if any(w in lower for w in ["long only", "no short", "only long"]):
            intent.constraints.append("long_only")
        if any(w in lower for w in ["short only", "only short"]):
            intent.constraints.append("short_only")

        # Confidence scoring
        intent.confidence = min(1.0, 0.3 + matched * 0.15)
        if matched == 0:
            intent.confidence = 0.4  # fallback defaults still reasonable

        return intent
