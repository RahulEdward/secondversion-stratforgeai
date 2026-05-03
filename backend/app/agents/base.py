"""Base types shared across all agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DataProfile:
    """Dataset characteristics computed by the DataAnalyst — no LLM needed."""

    n_bars: int = 0
    date_range: str = ""
    latest_close: float = 0.0
    # Indicators
    latest_rsi: float = 50.0
    avg_atr: float = 0.0
    atr_pct: float = 0.0          # ATR as % of close price
    avg_adx: float = 25.0
    bb_width_pct: float = 0.0     # Bollinger bandwidth as % of close
    ema50: float = 0.0
    ema200: float = 0.0
    # Derived regime classification
    regime: str = "unknown"        # "trending" | "ranging" | "volatile"
    trend_direction: str = "neutral"  # "bullish" | "bearish" | "neutral"

    def summary(self) -> str:
        """One-paragraph text for the architect LLM."""
        return (
            f"Dataset: {self.n_bars} bars, {self.date_range}. "
            f"Latest close={self.latest_close:.2f}, RSI={self.latest_rsi:.1f}. "
            f"ATR={self.avg_atr:.2f} ({self.atr_pct:.2f}% of price). "
            f"ADX={self.avg_adx:.1f} → regime={self.regime}. "
            f"EMA50={self.ema50:.2f}, EMA200={self.ema200:.2f} → "
            f"trend={self.trend_direction}. "
            f"BB width={self.bb_width_pct:.2f}% of price."
        )


@dataclass
class PipelineResult:
    """Compact result from a single run_full_pipeline call."""

    variant_name: str = ""
    spec: Dict[str, Any] = field(default_factory=dict)
    backtest_id: Optional[str] = None
    optimization_id: Optional[str] = None
    walk_forward_id: Optional[str] = None
    monte_carlo_id: Optional[str] = None
    grade: str = "F"
    verdict: str = "reject"
    score: float = 0.0
    vetos: List[Dict[str, str]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    wfe: Optional[float] = None
    mc_survival: Optional[float] = None
    mc_p_value: Optional[float] = None
    report_url: Optional[str] = None
    error: Optional[str] = None
    elapsed_sec: float = 0.0

    @property
    def passing(self) -> bool:
        """Strategy meets default acceptance criteria."""
        return self.verdict == "adopt" or self.grade in {
            "A+", "A", "A-", "B+", "B", "B-",
        }

    def failure_summary(self) -> str:
        """Brief explanation of why this variant failed — fed to architect."""
        parts = [f"Grade={self.grade}, verdict={self.verdict}"]
        n_trades = self.metrics.get("num_trades") or self.metrics.get("n_trades", 0)
        parts.append(f"trades={n_trades}")
        if self.metrics.get("sharpe") is not None:
            parts.append(f"sharpe={self.metrics['sharpe']:.2f}")
        if self.metrics.get("max_drawdown") is not None:
            parts.append(f"maxDD={self.metrics['max_drawdown']:.2%}")
        if self.metrics.get("profit_factor") is not None:
            parts.append(f"PF={self.metrics['profit_factor']:.2f}")
        if self.wfe is not None:
            parts.append(f"WFE={self.wfe:.2f}")
        if self.mc_survival is not None:
            parts.append(f"MC_survival={self.mc_survival:.1%}")
        for v in self.vetos:
            parts.append(f"VETO: {v.get('rule', '?')}: {v.get('message', '?')}")
        return " | ".join(parts)
