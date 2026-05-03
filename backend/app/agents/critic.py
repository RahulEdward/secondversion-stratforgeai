"""CriticAgent — deep quality analysis beyond simple metric checks.

Detects overfitting, instability, poor risk control, and structural flaws.
Returns a CriticVerdict with decision (accept/improve/reject), scores,
issues, and actionable improvements for the Evolver/Architect.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import DataProfile, PipelineResult


@dataclass
class CriticVerdict:
    decision: str = "reject"
    overfitting_score: float = 1.0
    instability_score: float = 1.0
    risk_control_score: float = 0.0
    structural_score: float = 0.0
    overall_confidence: float = 0.0
    issues: List[Dict[str, str]] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)

    @property
    def composite_score(self) -> float:
        overfit_ok = max(0.0, 1.0 - self.overfitting_score)
        stability_ok = max(0.0, 1.0 - self.instability_score)
        return overfit_ok * 25 + stability_ok * 25 + self.risk_control_score * 30 + self.structural_score * 20


def _count_conditions(group: Dict[str, Any]) -> int:
    count = 0
    for key in ("all_of", "any_of"):
        for item in group.get(key, []):
            count += 1 if "indicator" in item else _count_conditions(item)
    return count


def _extract_indicators(group: Dict[str, Any]) -> set:
    indicators: set = set()
    for key in ("all_of", "any_of"):
        for item in group.get(key, []):
            if "indicator" in item and item["indicator"] != "price":
                indicators.add(item["indicator"])
            elif "indicator" not in item:
                indicators |= _extract_indicators(item)
    return indicators


def _stop_value(stop: Dict[str, Any]) -> Optional[float]:
    stype = stop.get("type", "")
    if stype == "fixed_pct":
        return stop.get("value")
    if stype in ("atr", "trailing_atr"):
        return stop.get("multiplier", 2.0) * 0.01
    return stop.get("value")


def _infer_strategy_type(entries: Dict[str, Any]) -> str:
    indicators = _extract_indicators(entries)
    trend = {"ema", "sma", "macd", "supertrend", "ichimoku", "adx"}
    meanrev = {"rsi", "bollinger_bands", "stochastic", "williams_r", "cci"}
    tc = len(indicators & trend)
    mc = len(indicators & meanrev)
    if tc > mc:
        return "trend_following"
    if mc > tc:
        return "mean_reversion"
    return "mixed"


class CriticAgent:
    def review(self, result: PipelineResult, profile: Optional[DataProfile] = None) -> CriticVerdict:
        if result.error:
            return CriticVerdict(decision="reject", issues=[{"category": "error", "detail": result.error}],
                                 improvements=["Fix the underlying error before re-testing."])
        issues: List[Dict[str, str]] = []
        improvements: List[str] = []

        overfit = self._check_overfitting(result, issues, improvements)
        instability = self._check_instability(result, issues, improvements)
        risk_score = self._check_risk_control(result, issues, improvements)
        structural = self._check_structure(result, profile, issues, improvements)
        decision = self._decide(overfit, instability, risk_score, structural, result)
        confidence = self._compute_confidence(result)

        return CriticVerdict(decision=decision, overfitting_score=overfit, instability_score=instability,
                             risk_control_score=risk_score, structural_score=structural,
                             overall_confidence=confidence, issues=issues, improvements=improvements)

    def review_batch(self, results: List[PipelineResult], profile: Optional[DataProfile] = None) -> List[CriticVerdict]:
        return [self.review(r, profile) for r in results]

    def _check_overfitting(self, r: PipelineResult, issues, improvements) -> float:
        score = 0.0
        if r.wfe is not None:
            if r.wfe < 0.3:
                score = max(score, 0.9)
                issues.append({"category": "overfitting", "detail": f"WFE={r.wfe:.2f} — severe overfit, OOS retains <30% of IS edge."})
                improvements.append("Simplify strategy: max 2 entry conditions, wider param ranges.")
            elif r.wfe < 0.5:
                score = max(score, 0.6)
                issues.append({"category": "overfitting", "detail": f"WFE={r.wfe:.2f} — moderate overfitting."})
                improvements.append("Reduce optimization grid granularity, remove one condition.")

        n_conds = _count_conditions(r.spec.get("entries", {})) + _count_conditions(r.spec.get("exits", {}))
        if n_conds > 6:
            score = max(score, 0.7)
            issues.append({"category": "overfitting", "detail": f"{n_conds} conditions — high complexity overfitting risk."})
            improvements.append("Reduce to 2-3 entry + 1-2 exit conditions.")
        elif n_conds > 4:
            score = max(score, 0.4)

        if r.mc_survival is not None and r.mc_survival < 0.7:
            score = max(score, 0.5)
            issues.append({"category": "overfitting", "detail": f"MC survival={r.mc_survival:.1%} — signal may be noise."})
            improvements.append("Add regime filter (ADX > 20) to filter noisy periods.")
        return min(1.0, score)

    def _check_instability(self, r: PipelineResult, issues, improvements) -> float:
        score = 0.0
        m = r.metrics
        sharpe, sortino = m.get("sharpe"), m.get("sortino")
        if sharpe and sortino and float(sharpe) > 0:
            ratio = float(sortino) / float(sharpe)
            if ratio < 0.8:
                score = max(score, 0.5)
                issues.append({"category": "instability", "detail": f"Sortino/Sharpe={ratio:.2f} — hidden downside risk."})
                improvements.append("Add trailing stop to protect against sharp reversals.")

        max_dd = m.get("max_drawdown")
        if max_dd is not None:
            dd = abs(float(max_dd))
            if dd > 0.30:
                score = max(score, 0.7)
                issues.append({"category": "instability", "detail": f"Max DD={float(max_dd):.1%} — exceeds 30% threshold."})
                improvements.append("Reduce position size to 0.5-0.7, tighten stop-loss.")
            elif dd > 0.20:
                score = max(score, 0.4)

        wr = m.get("win_rate")
        if wr is not None and float(wr) < 0.35:
            score = max(score, 0.5)
            issues.append({"category": "instability", "detail": f"Win rate={float(wr):.1%} — needs high R:R to compensate."})
            improvements.append("Ensure take_profit >= 3x stop_loss for low win-rate strategies.")

        if m.get("num_trades", 0) < 50:
            score = max(score, 0.4)
            issues.append({"category": "instability", "detail": f"Only {m.get('num_trades', 0)} trades — low statistical confidence."})
            improvements.append("Loosen entry thresholds to generate more signals.")
        return min(1.0, score)

    def _check_risk_control(self, r: PipelineResult, issues, improvements) -> float:
        score = 0.0
        stops = r.spec.get("stops", {})
        sizing = r.spec.get("sizing", {})

        if stops.get("stop_loss"):
            score += 0.35
            if stops["stop_loss"].get("type") in ("atr", "trailing_atr"):
                score += 0.05
        else:
            issues.append({"category": "risk_control", "detail": "NO STOP-LOSS — unlimited downside risk."})
            improvements.append("ADD STOP-LOSS: ATR-based, multiplier 1.5-3.0, period 14.")

        if stops.get("take_profit"):
            score += 0.15
        else:
            improvements.append("Add take_profit (fixed_pct 0.03-0.06 or rr_ratio).")

        if stops.get("trailing"):
            score += 0.10

        sl, tp = stops.get("stop_loss"), stops.get("take_profit")
        if sl and tp:
            sv, tv = _stop_value(sl), _stop_value(tp)
            if sv and tv and sv > 0:
                rr = tv / sv
                if rr >= 2.0:
                    score += 0.10
                elif rr < 1.0:
                    issues.append({"category": "risk_control", "detail": f"R:R={rr:.2f} — risking more than potential gain."})
                    improvements.append("Increase TP or decrease SL for at least 1:1.5 R:R.")

        sv = sizing.get("value", 1.0)
        if sv > 0.95:
            issues.append({"category": "risk_control", "detail": f"Position size={sv:.0%} — near full equity per trade."})
            improvements.append("Reduce sizing.value to 0.5-0.8.")
        elif sv <= 0.80:
            score += 0.10
        if sizing.get("type") in ("vol_target", "kelly"):
            score += 0.10

        if r.spec.get("fees_override") and r.spec["fees_override"] > 0:
            score += 0.05
        return min(1.0, score)

    def _check_structure(self, r: PipelineResult, profile, issues, improvements) -> float:
        score = 0.0
        entries = r.spec.get("entries", {})
        exits = r.spec.get("exits", {})

        if r.spec.get("name"):
            score += 0.05
        n_entry = _count_conditions(entries)
        n_exit = _count_conditions(exits)
        if n_entry >= 2:
            score += 0.20
        elif n_entry == 1:
            score += 0.10
            improvements.append("Add confirmation condition (ADX > 20, volume filter).")
        if n_exit >= 1:
            score += 0.15

        all_ind = _extract_indicators(entries) | _extract_indicators(exits)
        if len(all_ind) >= 3:
            score += 0.15
        elif len(all_ind) == 2:
            score += 0.10

        for pair, reason in [
            ({"rsi", "stochastic"}, "RSI & Stochastic are redundant oscillators"),
            ({"sma", "ema"}, "SMA & EMA are redundant moving averages"),
        ]:
            if pair.issubset(all_ind):
                score = max(0, score - 0.10)
                issues.append({"category": "structure", "detail": f"Redundant: {reason}."})

        if r.spec.get("regime_filter"):
            score += 0.15

        if profile:
            stype = _infer_strategy_type(entries)
            if stype == "trend_following" and profile.regime == "ranging":
                issues.append({"category": "structure", "detail": "Trend strategy on ranging market — expect whipsaws."})
                improvements.append("Add regime filter (ADX > 25) or switch to mean-reversion.")
            elif stype == "mean_reversion" and profile.regime == "trending":
                issues.append({"category": "structure", "detail": "Mean-reversion on trending market — fights the trend."})
                improvements.append("Add regime filter (ADX < 20) or switch to trend-following.")

        pf = r.metrics.get("profit_factor")
        if pf and float(pf) >= 1.5:
            score += 0.15
        elif pf and float(pf) >= 1.2:
            score += 0.10
        return min(1.0, score)

    def _decide(self, overfit, instability, risk, structural, result) -> str:
        if risk < 0.20:
            return "reject"
        if overfit > 0.8:
            return "reject"
        grade_ok = result.grade in {"A+", "A", "A-", "B+", "B", "B-"}
        if grade_ok and overfit < 0.4 and instability < 0.5 and risk >= 0.50 and structural >= 0.40:
            return "accept"
        return "improve"

    def _compute_confidence(self, r: PipelineResult) -> float:
        conf = 0.3
        n = r.metrics.get("num_trades", 0)
        if n >= 100: conf += 0.3
        elif n >= 50: conf += 0.2
        elif n >= 20: conf += 0.1
        if r.wfe is not None: conf += 0.15
        if r.mc_survival is not None: conf += 0.15
        return min(1.0, conf)
