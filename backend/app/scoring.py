"""Strategy verdict engine (Phase 7, Slice 6).

The job of this module is to translate the raw metrics coming out of
`backtest.py`, `optimize.py`, and `validate.py` into a single, human-
understandable judgement so the AI can make a confident adopt / iterate /
reject call — and so the report layer can print a letter grade.

Design goals:
    - Deterministic: same inputs -> same verdict. No randomness.
    - Veto-first: *any* hard-fail (e.g. max drawdown > 50%, fewer than 10
      trades, OOS loses money) immediately collapses the grade to F
      regardless of surface-level Sharpe. Production-grade reliability
      prefers false negatives over false positives.
    - Multi-metric: the positive score is a weighted blend of Sharpe,
      Sortino, Calmar, profit factor, expectancy, win rate; *not* any
      single headline number.
    - Out-of-sample aware: if a Monte Carlo result or walk-forward
      result is supplied, its p-value / WFE is folded into the verdict.
      In-sample-only scores cap at a B+ — a production strategy *must*
      clear OOS to get an A.
    - Transparent: we emit every component score and every veto so the
      user (and the AI) can see exactly what pulled the grade up or down.

Contracts:
    score_backtest(metrics, significance, *, ...) -> ScoringResult
    score_full(bt_metrics, bt_significance, *, mc=None, wf=None, ...)
                                                  -> ScoringResult

Grades are A+, A, A-, B+, B, B-, C+, C, C-, D, F (11 buckets). Anything
with a hard-veto returns F.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ─── Thresholds (production-grade defaults) ─────────────────────────────

# Hard-veto thresholds: breach any of these => grade F, verdict="reject".
# Tuned to match the AI-Backtester-Flow diagram's "Smart Validation Rules":
#   - Minimum Trades Rule: At least 100 Trades Required
#   - Data Usage Rule:     Must use > 70% of Total Dataset (we use trade
#                          coverage; 0.0 means literally zero signals)
#   - Walk-Forward Rule:   Out-of-Sample Profit Must be Positive
#   - Monte Carlo Rule:    Survival Rate > 90% AND DD-within-limit > 70%
#   - Overfitting Check:   WFE >= 0.5 (OOS at least half of IS)
VETO_MIN_TRADES = 100
VETO_MIN_DATA_USAGE = 0.0          # any trades cover at least one bar
VETO_MAX_DRAWDOWN = -0.50          # -50% equity peak-to-trough
VETO_MIN_TOTAL_RETURN = -0.30      # -30% total return (allow some DD stress)
VETO_NON_POSITIVE_PF = 1.0         # profit factor must exceed 1.0
VETO_MIN_MC_SURVIVAL = 0.90        # 90% of MC iterations end profitable
VETO_MIN_MC_DD_WITHIN = 0.70       # 70% of MC iterations stay within DD limit
VETO_MIN_WFE = 0.5                 # walk-forward efficiency floor

# Score weights (sum does not need to be 1; we normalise by max possible).
# Heavy weight on risk-adjusted metrics; modest on win rate (easy to game).
# NB: we use `avg_trade` (per-trade fractional return) — NOT VectorBT's
# `expectancy`, which is in PnL currency units and not comparable across
# account sizes.
METRIC_WEIGHTS: Dict[str, float] = {
    "sharpe": 3.0,
    "sortino": 2.0,
    "calmar": 2.0,
    "profit_factor": 1.5,
    "avg_trade": 1.0,
    "win_rate": 0.5,
    "num_trades": 0.5,   # more trades == higher confidence (soft)
}

# Per-metric "excellent" thresholds — a metric at this value scores 1.0.
# Values above saturate at 1.0 to avoid one giant number dominating.
EXCELLENT: Dict[str, float] = {
    "sharpe": 2.0,
    "sortino": 3.0,
    "calmar": 2.0,
    "profit_factor": 2.5,
    "avg_trade": 0.02,   # 2% mean trade return
    "win_rate": 0.60,
    "num_trades": 100.0,
}

# Per-metric "unacceptable" — a metric at-or-below this scores 0.0.
UNACCEPTABLE: Dict[str, float] = {
    "sharpe": 0.0,
    "sortino": 0.0,
    "calmar": 0.0,
    "profit_factor": 1.0,
    "avg_trade": 0.0,
    "win_rate": 0.30,
    "num_trades": VETO_MIN_TRADES,
}


# ─── Result types ───────────────────────────────────────────────────────


@dataclass
class Veto:
    rule: str
    message: str


@dataclass
class ComponentScore:
    metric: str
    raw_value: Optional[float]
    normalised: float       # 0..1
    weight: float
    contribution: float     # normalised * weight


@dataclass
class ScoringResult:
    score: float                         # 0..100
    grade: str                           # A+ .. F
    verdict: str                         # adopt | iterate | reject
    headline: str                        # one-sentence summary
    vetos: List[Veto]
    components: List[ComponentScore]
    in_sample_score: float               # 0..100, before OOS adjustments
    oos_adjustment: float                # additive +/- to in_sample_score
    confidence: str                      # low | medium | high
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─── Helpers ────────────────────────────────────────────────────────────


def _normalise(
    metric: str,
    value: Optional[float],
) -> float:
    """Map a raw metric to [0, 1] using linear interpolation between
    UNACCEPTABLE and EXCELLENT anchors. Out-of-range -> clamped."""
    if value is None:
        return 0.0
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(v) or math.isinf(v):
        return 0.0
    lo = UNACCEPTABLE[metric]
    hi = EXCELLENT[metric]
    if hi == lo:
        return 1.0 if v >= hi else 0.0
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


def _grade(score: float) -> str:
    """Score (0..100) -> letter grade. Calibrated so a clean
    Sharpe~1.5 + solid PF strategy lands in the B+/A- range."""
    if score >= 90: return "A+"
    if score >= 85: return "A"
    if score >= 80: return "A-"
    if score >= 75: return "B+"
    if score >= 70: return "B"
    if score >= 65: return "B-"
    if score >= 60: return "C+"
    if score >= 55: return "C"
    if score >= 50: return "C-"
    if score >= 40: return "D"
    return "F"


def _verdict_from_grade(grade: str, has_vetos: bool, oos_ok: bool) -> str:
    """adopt / iterate / reject mapping."""
    if has_vetos or grade == "F":
        return "reject"
    if grade.startswith("A") and oos_ok:
        return "adopt"
    return "iterate"


def _apply_vetos(
    metrics: Dict[str, Any],
    *,
    mc: Optional[Dict[str, Any]] = None,
    wf: Optional[Dict[str, Any]] = None,
) -> List[Veto]:
    """Hard-rule gates — any breach => grade F + verdict=reject.

    Implements every "Smart Validation Rule" the AI-Backtester-Flow
    diagram lists. ``mc`` and ``wf`` are optional; when supplied the
    extra rules (Monte-Carlo survival, walk-forward edge / overfit) get
    evaluated, otherwise we only assert the in-sample-only rules.
    """
    v: List[Veto] = []

    # ── In-sample (always evaluated) ──
    n_trades = metrics.get("num_trades")
    if n_trades is None or int(n_trades) < VETO_MIN_TRADES:
        v.append(Veto(
            rule="min_trades",
            message=(
                f"Only {n_trades} trades — need at least {VETO_MIN_TRADES} "
                "for any statistical claim (Smart Validation Rule)."
            ),
        ))

    data_usage = metrics.get("data_usage_pct")
    if data_usage is not None and float(data_usage) <= VETO_MIN_DATA_USAGE:
        v.append(Veto(
            rule="data_usage",
            message=(
                f"Data usage {float(data_usage):.1%} — strategy never holds "
                "a position; no edge to measure."
            ),
        ))

    mdd = metrics.get("max_drawdown")
    if mdd is not None and float(mdd) < VETO_MAX_DRAWDOWN:
        v.append(Veto(
            rule="max_drawdown",
            message=(
                f"Max drawdown {float(mdd):.2%} exceeds production floor "
                f"{VETO_MAX_DRAWDOWN:.0%}."
            ),
        ))

    tr = metrics.get("total_return")
    if tr is not None and float(tr) < VETO_MIN_TOTAL_RETURN:
        v.append(Veto(
            rule="min_total_return",
            message=(
                f"Total return {float(tr):.2%} below acceptable floor "
                f"{VETO_MIN_TOTAL_RETURN:.0%}."
            ),
        ))

    pf = metrics.get("profit_factor")
    if pf is not None and float(pf) <= VETO_NON_POSITIVE_PF:
        v.append(Veto(
            rule="profit_factor",
            message=(
                f"Profit factor {float(pf):.3f} <= {VETO_NON_POSITIVE_PF} — "
                "losers outweigh winners."
            ),
        ))

    # ── Monte-Carlo gates (when available) ──
    if mc is not None:
        survival = mc.get("survival_rate")
        if survival is not None and float(survival) < VETO_MIN_MC_SURVIVAL:
            v.append(Veto(
                rule="mc_survival",
                message=(
                    f"Monte-Carlo survival {float(survival):.1%} below "
                    f"{VETO_MIN_MC_SURVIVAL:.0%} — too many resampled "
                    "paths end in a loss."
                ),
            ))
        dd_in = mc.get("dd_within_limit_rate")
        if dd_in is not None and float(dd_in) < VETO_MIN_MC_DD_WITHIN:
            v.append(Veto(
                rule="mc_dd_within_limit",
                message=(
                    f"Only {float(dd_in):.1%} of MC paths stayed within the "
                    f"DD limit (need {VETO_MIN_MC_DD_WITHIN:.0%})."
                ),
            ))

    # ── Walk-forward gates (when available) ──
    if wf is not None:
        agg = wf.get("aggregate") or {}
        oos_total = agg.get("out_sample_total_return") or agg.get("oos_total_return")
        if oos_total is not None and float(oos_total) <= 0:
            v.append(Veto(
                rule="walk_forward_oos_negative",
                message=(
                    f"OOS total return {float(oos_total):.2%} <= 0 — "
                    "strategy fails the walk-forward profitability rule."
                ),
            ))
        wfe = wf.get("wfe")
        if wfe is not None and float(wfe) < VETO_MIN_WFE:
            v.append(Veto(
                rule="overfitting",
                message=(
                    f"Walk-forward efficiency {float(wfe):.2f} < "
                    f"{VETO_MIN_WFE} — OOS far below IS, likely overfit."
                ),
            ))

    return v


def _confidence(
    metrics: Dict[str, Any],
    significance: Dict[str, Any],
    mc: Optional[Dict[str, Any]],
    wf: Optional[Dict[str, Any]],
) -> Tuple[str, List[str]]:
    """Overall confidence level + reasons."""
    reasons: List[str] = []
    level = "low"

    n = int(metrics.get("num_trades") or 0)
    if n >= 100:
        reasons.append(f"{n} trades (healthy sample)")
    elif n >= 30:
        reasons.append(f"{n} trades (moderate sample)")
    else:
        reasons.append(f"{n} trades (small sample)")

    sig_90 = bool(significance.get("is_significant_90"))
    sig_95 = bool(significance.get("is_significant_95"))
    if sig_95:
        reasons.append("trade-level t-test significant at 95%")
    elif sig_90:
        reasons.append("trade-level t-test significant at 90%")
    else:
        reasons.append("trade-level t-test NOT significant at 90%")

    if mc is not None:
        p = mc.get("p_value_positive_mean")
        if p is not None and p < 0.05:
            reasons.append(f"Monte Carlo p={float(p):.3f} (95% confident)")
        elif p is not None and p < 0.10:
            reasons.append(f"Monte Carlo p={float(p):.3f} (90% confident)")
        elif p is not None:
            reasons.append(f"Monte Carlo p={float(p):.3f} (insignificant)")

    if wf is not None:
        wfe = wf.get("wfe")
        oos = (wf.get("aggregate") or {}).get("oos_mean_sharpe")
        if wfe is not None and oos is not None:
            reasons.append(f"WFE={float(wfe):.2f}, OOS Sharpe={float(oos):.2f}")

    # Decide overall level.
    has_oos_validation = (mc is not None) or (wf is not None)
    if n >= 30 and sig_90 and has_oos_validation:
        level = "high"
    elif n >= 20 and (sig_90 or has_oos_validation):
        level = "medium"
    else:
        level = "low"

    return level, reasons


# ─── Core scoring ───────────────────────────────────────────────────────


def _compute_in_sample_score(
    metrics: Dict[str, Any],
) -> Tuple[float, List[ComponentScore]]:
    """Weighted blend of normalised metric values -> 0..100."""
    components: List[ComponentScore] = []
    total_weight = 0.0
    weighted_sum = 0.0
    for metric, weight in METRIC_WEIGHTS.items():
        raw = metrics.get(metric)
        norm = _normalise(metric, raw)
        contribution = norm * weight
        components.append(ComponentScore(
            metric=metric,
            raw_value=None if raw is None else float(raw),
            normalised=float(norm),
            weight=float(weight),
            contribution=float(contribution),
        ))
        total_weight += weight
        weighted_sum += contribution
    in_sample_score = 100.0 * weighted_sum / total_weight if total_weight > 0 else 0.0
    return in_sample_score, components


def _oos_adjustment(
    mc: Optional[Dict[str, Any]],
    wf: Optional[Dict[str, Any]],
) -> Tuple[float, List[str]]:
    """Return (additive_score_delta, notes). Range roughly [-20, +10]."""
    delta = 0.0
    notes: List[str] = []

    # Monte Carlo: reward low p-values, penalise high.
    if mc is not None:
        p = mc.get("p_value_positive_mean")
        exp_tr = mc.get("expected_total_return")
        if p is not None:
            if p < 0.05:
                delta += 5.0
                notes.append(f"+5.0 MC p={p:.3f} clears 95%")
            elif p < 0.10:
                delta += 2.0
                notes.append(f"+2.0 MC p={p:.3f} clears 90%")
            elif p > 0.30:
                delta -= 10.0
                notes.append(f"-10.0 MC p={p:.3f} very weak edge")
            elif p > 0.20:
                delta -= 5.0
                notes.append(f"-5.0 MC p={p:.3f} weak edge")
        if exp_tr is not None and float(exp_tr) <= 0:
            delta -= 15.0
            notes.append(f"-15.0 MC expected total return {float(exp_tr):.2%} non-positive")

    # Walk-forward: reward WFE in [0.5, 1.2], penalise below 0.3 or OOS negative.
    if wf is not None:
        wfe = wf.get("wfe")
        agg = wf.get("aggregate") or {}
        oos_sh = agg.get("oos_mean_sharpe")
        oos_tr = agg.get("oos_mean_total_return")

        if wfe is not None:
            if 0.7 <= wfe <= 1.3:
                delta += 5.0
                notes.append(f"+5.0 WFE {wfe:.2f} in robust band")
            elif 0.5 <= wfe < 0.7:
                delta += 2.0
                notes.append(f"+2.0 WFE {wfe:.2f} acceptable")
            elif 0.3 <= wfe < 0.5:
                delta -= 10.0
                notes.append(f"-10.0 WFE {wfe:.2f} moderate overfit")
            else:
                delta -= 25.0
                notes.append(f"-25.0 WFE {wfe:.2f} severe overfit or regime tail")
        if oos_sh is not None:
            if float(oos_sh) <= 0:
                delta -= 25.0
                notes.append(f"-25.0 OOS mean Sharpe {float(oos_sh):.2f} non-positive")
            elif float(oos_sh) < 0.5:
                delta -= 10.0
                notes.append(f"-10.0 OOS mean Sharpe {float(oos_sh):.2f} below 0.5")
        if oos_tr is not None and float(oos_tr) < 0:
            delta -= 10.0
            notes.append(f"-10.0 OOS mean total return {float(oos_tr):.2%} negative")

    # Cap the boost in-sample-only would be unfair.
    delta = max(-40.0, min(delta, 15.0))
    return delta, notes


def score_backtest(
    metrics: Dict[str, Any],
    significance: Dict[str, Any],
    *,
    mc: Optional[Dict[str, Any]] = None,
    wf: Optional[Dict[str, Any]] = None,
) -> ScoringResult:
    """Produce a verdict for a single backtest, optionally with MC / WF context.

    Args:
        metrics: `BacktestResult.metrics` dict.
        significance: `BacktestResult.significance` dict.
        mc: optional `MonteCarloResult.to_dict()`.
        wf: optional `WalkForwardResult.to_dict()`.
    """
    vetos = _apply_vetos(metrics, mc=mc, wf=wf)

    in_sample_score, components = _compute_in_sample_score(metrics)
    oos_delta, oos_notes = _oos_adjustment(mc, wf)

    # If we have no OOS validation, cap the score so in-sample hero specs
    # can't walk away with an A. B+ is the ceiling without OOS evidence.
    has_oos = (mc is not None) or (wf is not None)
    raw_total = in_sample_score + oos_delta
    if not has_oos:
        raw_total = min(raw_total, 78.0)

    # Significance bonus: modest — max +3 — to avoid rewarding only-lucky winners.
    sig_bonus = 0.0
    if significance.get("is_significant_95"):
        sig_bonus = 3.0
    elif significance.get("is_significant_90"):
        sig_bonus = 1.5
    raw_total += sig_bonus

    # Clamp final to 0..100.
    raw_total = max(0.0, min(100.0, raw_total))

    # If any veto, force F.
    if vetos:
        final_score = 0.0
        grade = "F"
    else:
        final_score = raw_total
        grade = _grade(final_score)

    # For `adopt`, we require OOS evidence of a real edge — not just a
    # positive-but-trivial mean Sharpe. Below these floors we downgrade to
    # `iterate` even if the headline score looks good.
    oos_ok = True
    if wf is not None:
        agg = wf.get("aggregate") or {}
        oos_sh = agg.get("oos_mean_sharpe")
        wfe = wf.get("wfe")
        if oos_sh is None or float(oos_sh) < 0.5:
            oos_ok = False
        if wfe is None or float(wfe) < 0.5:
            oos_ok = False
    if mc is not None:
        etr = mc.get("expected_total_return")
        pval = mc.get("p_value_positive_mean")
        if etr is None or float(etr) <= 0:
            oos_ok = False
        if pval is None or float(pval) > 0.10:
            oos_ok = False

    verdict = _verdict_from_grade(grade, bool(vetos), oos_ok)
    confidence, conf_notes = _confidence(metrics, significance, mc, wf)

    # Headline.
    n = int(metrics.get("num_trades") or 0)
    sharpe = metrics.get("sharpe")
    mdd = metrics.get("max_drawdown")
    pf = metrics.get("profit_factor")
    if vetos:
        headline = (
            f"REJECT: {vetos[0].message}"
        )
    else:
        sh = f"{float(sharpe):.2f}" if sharpe is not None else "n/a"
        dd = f"{float(mdd):.1%}" if mdd is not None else "n/a"
        pff = f"{float(pf):.2f}" if pf is not None else "n/a"
        headline = (
            f"Grade {grade} ({verdict.upper()}): Sharpe {sh}, PF {pff}, "
            f"MaxDD {dd}, {n} trades, {confidence} confidence."
        )

    notes = list(oos_notes)
    if sig_bonus:
        notes.append(f"+{sig_bonus:.1f} trade-level significance bonus")
    if not has_oos:
        notes.append("Score capped at B+ ceiling — no OOS validation supplied")
    notes.extend(conf_notes)

    return ScoringResult(
        score=float(final_score),
        grade=grade,
        verdict=verdict,
        headline=headline,
        vetos=vetos,
        components=components,
        in_sample_score=float(in_sample_score),
        oos_adjustment=float(oos_delta + sig_bonus),
        confidence=confidence,
        notes=notes,
    )


def score_from_result_dicts(
    bt: Dict[str, Any],
    *,
    mc: Optional[Dict[str, Any]] = None,
    wf: Optional[Dict[str, Any]] = None,
) -> ScoringResult:
    """Convenience wrapper — takes a persisted `bt_<id>.json` dict."""
    return score_backtest(
        bt.get("metrics") or {},
        bt.get("significance") or {},
        mc=mc,
        wf=wf,
    )


# ─── CLI smoke ──────────────────────────────────────────────────────────


def _smoke() -> None:
    """`python -m app.scoring` — exercises all grade paths with synthetic inputs."""

    # Case 1 — insufficient trades -> veto -> F.
    r1 = score_backtest(
        metrics={"num_trades": 3, "sharpe": 5.0, "sortino": 6.0,
                 "calmar": 10.0, "profit_factor": 10.0, "avg_trade": 0.05,
                 "win_rate": 0.8, "total_return": 0.5, "max_drawdown": -0.05},
        significance={"is_significant_95": True},
    )
    assert r1.grade == "F" and r1.verdict == "reject"
    print(f"Case 1 (few trades): {r1.headline}")

    # Case 2 — deep drawdown -> veto.
    r2 = score_backtest(
        metrics={"num_trades": 50, "sharpe": 2.0, "sortino": 3.0,
                 "calmar": 0.5, "profit_factor": 1.5, "avg_trade": 0.01,
                 "win_rate": 0.55, "total_return": 0.3, "max_drawdown": -0.60},
        significance={"is_significant_95": True},
    )
    assert r2.grade == "F" and r2.verdict == "reject"
    print(f"Case 2 (deep DD): {r2.headline}")

    # Case 3 — decent in-sample, no OOS -> capped at ~B+.
    r3 = score_backtest(
        metrics={"num_trades": 60, "sharpe": 1.6, "sortino": 2.2,
                 "calmar": 1.4, "profit_factor": 1.8, "avg_trade": 0.012,
                 "win_rate": 0.55, "total_return": 0.4, "max_drawdown": -0.15},
        significance={"is_significant_95": True, "is_significant_90": True},
    )
    print(f"Case 3 (IS only): score={r3.score:.1f} grade={r3.grade} "
          f"verdict={r3.verdict} conf={r3.confidence}")
    assert r3.grade in {"B+", "B", "B-"}, r3.grade

    # Case 4 — decent IS + solid MC + solid WF -> should reach A range.
    r4 = score_backtest(
        metrics={"num_trades": 120, "sharpe": 1.8, "sortino": 2.5,
                 "calmar": 1.6, "profit_factor": 2.0, "avg_trade": 0.015,
                 "win_rate": 0.58, "total_return": 0.55, "max_drawdown": -0.18},
        significance={"is_significant_95": True},
        mc={"p_value_positive_mean": 0.02, "expected_total_return": 0.45},
        wf={"wfe": 0.85, "aggregate": {"oos_mean_sharpe": 1.4,
                                       "oos_mean_total_return": 0.3}},
    )
    print(f"Case 4 (IS + OOS good): score={r4.score:.1f} grade={r4.grade} "
          f"verdict={r4.verdict} conf={r4.confidence}")
    assert r4.grade.startswith("A"), r4.grade
    assert r4.verdict == "adopt"

    # Case 5 — great IS but WF shows overfit -> should drop grade + iterate.
    r5 = score_backtest(
        metrics={"num_trades": 120, "sharpe": 2.5, "sortino": 3.5,
                 "calmar": 2.2, "profit_factor": 2.5, "avg_trade": 0.02,
                 "win_rate": 0.62, "total_return": 0.9, "max_drawdown": -0.12},
        significance={"is_significant_95": True},
        wf={"wfe": 0.15, "aggregate": {"oos_mean_sharpe": 0.2,
                                       "oos_mean_total_return": 0.01}},
    )
    print(f"Case 5 (overfit WF): score={r5.score:.1f} grade={r5.grade} "
          f"verdict={r5.verdict}")
    assert r5.verdict in {"iterate", "reject"}, r5.verdict

    # Case 6 — OOS loses money -> reject.
    r6 = score_backtest(
        metrics={"num_trades": 100, "sharpe": 1.5, "sortino": 2.0,
                 "calmar": 1.2, "profit_factor": 1.7, "avg_trade": 0.01,
                 "win_rate": 0.52, "total_return": 0.35, "max_drawdown": -0.20},
        significance={"is_significant_90": True},
        wf={"wfe": 0.5, "aggregate": {"oos_mean_sharpe": -0.3,
                                      "oos_mean_total_return": -0.05}},
    )
    print(f"Case 6 (OOS loses): score={r6.score:.1f} grade={r6.grade} "
          f"verdict={r6.verdict}")
    assert r6.verdict in {"iterate", "reject"}

    print("SCORING SMOKE OK")


if __name__ == "__main__":
    _smoke()
